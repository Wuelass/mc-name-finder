"""Public CLI; discovery and authenticated confirmation are deliberately separate."""

import argparse
import json
import math
import os
import subprocess
from contextlib import nullcontext
from pathlib import Path

from dotenv import load_dotenv
from filelock import Timeout
from rich.console import Console
from rich.progress import track
from rich.table import Table

from . import __version__
from .api import ApiError, MinecraftClient, valid_username
from .auth import AccountToken, AuthError, login, logout, profile_lock, setup_helper
from .storage import atomic_write, checkpoint, export_report, load_report, utc_now
from .watch import parse_start, run_watch
from .words import generate, rank

console = Console(highlight=False)


def bounded_float(minimum: float, maximum: float | None = None):
    def parse(value: str) -> float:
        number = float(value)
        if (
            not math.isfinite(number)
            or number < minimum
            or (maximum is not None and number > maximum)
        ):
            raise argparse.ArgumentTypeError(f"Expected a finite number >= {minimum}")
        return number

    return parse


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Find English and French word-based Minecraft Java usernames."
    )
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="Discover words and check public profile occupancy")
    scan.add_argument("--languages", nargs="+", choices=["en", "fr"], default=["en", "fr"])
    scan.add_argument("--min-length", "--min", type=int, default=2)
    scan.add_argument(
        "--max-length",
        "--max",
        type=int,
        default=10,
        help="Maximum normalized length (default: 10, up to 16)",
    )
    scan.add_argument(
        "--min-frequency",
        type=bounded_float(0, 8),
        default=0.0,
        help="Minimum Zipf frequency (0 = all corpus candidates)",
    )
    scan.add_argument("--limit", type=positive_int, help="Check only the highest-ranked N words")
    scan.add_argument("--words", type=Path, help="Use your UTF-8 word list instead of wordfreq")
    scan.add_argument("--output", type=Path, default=Path("results"))
    scan.add_argument(
        "--delay",
        type=bounded_float(1),
        default=1.0,
        help="Seconds between public requests (minimum: 1)",
    )
    mode = scan.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume", action="store_true", help="Continue saved selection; retain checks"
    )
    mode.add_argument("--overwrite", action="store_true", help="Start a fresh scan in this output")
    scan.add_argument("--dry-run", action="store_true", help="Generate words without any API calls")
    confirm = commands.add_parser(
        "confirm", help="Confirm selected names with your Minecraft token"
    )
    confirm.add_argument("--output", type=Path, default=Path("results"))
    confirm.add_argument("--top", type=positive_int, default=20)
    confirm.add_argument("--names", nargs="+", help="Check these names from the saved report")
    confirm.add_argument("--env-file", type=Path, default=Path(".env"))
    confirm.add_argument("--account", help="Use a saved Microsoft login instead of .env")
    confirm.add_argument("--delay", type=bounded_float(16), default=16.0)
    confirm.add_argument(
        "--refresh", action="store_true", help="Recheck previously confirmed names"
    )
    commands.add_parser("auth-setup", help="Install the pinned Microsoft login helper")
    signin = commands.add_parser("login", help="Connect your Minecraft account through Microsoft")
    signin.add_argument("--account", default="default", help="Local account alias")
    signin.add_argument("--no-browser", action="store_true", help="Print the link/code only")
    info = commands.add_parser("account", help="Show connected profile and name-change eligibility")
    info.add_argument("--account", default="default")
    signout = commands.add_parser("logout", help="Delete local cached credentials for an alias")
    signout.add_argument("--account", default="default")
    watch = commands.add_parser(
        "watch", help="Monitor one name; optionally claim it when available"
    )
    watch.add_argument("name", type=valid_username)
    watch.add_argument("--account", default="default")
    watch.add_argument(
        "--claim", action="store_true", help="Allow automatic name change on AVAILABLE"
    )
    watch.add_argument(
        "--expected-profile", help="Require this current Minecraft name before arming"
    )
    watch.add_argument(
        "--start-at", type=parse_start, help="ISO timestamp with timezone to start polling"
    )
    watch.add_argument("--interval", type=bounded_float(16), default=16.0)
    watch.add_argument(
        "--max-minutes", type=bounded_float(0.01), help="Stop after N polling minutes"
    )
    return root


def summary(candidates, output: Path) -> None:
    table = Table(title="Minecraft Java · scan results", header_style="bold cyan")
    for title in ("Letters", "Candidates", "Taken", "Unregistered*", "Available", "Unchecked"):
        table.add_column(title, justify="right")
    for length in sorted({len(c.name) for c in candidates}):
        rows = [c for c in candidates if len(c.name) == length]
        table.add_row(
            str(length),
            str(len(rows)),
            str(sum(c.lookup_status == "TAKEN" for c in rows)),
            str(sum(c.lookup_status == "UNREGISTERED" for c in rows)),
            str(sum(c.exact_status == "AVAILABLE" for c in rows)),
            str(sum(c.lookup_status == "UNKNOWN" for c in rows)),
        )
    console.print(table)
    console.print("* No current profile detected; may still be reserved or disallowed.")
    console.print("2-letter names are excluded from new-name availability checks.")
    console.print(f"Reports: {output.resolve()}", markup=False)


def scan(args) -> int:
    if not 2 <= args.min_length <= args.max_length <= 16:
        raise ValueError("Lengths must satisfy 2 <= min-length <= max-length <= 16.")
    if args.resume:
        candidates, metadata = load_report(args.output)
        console.print("Resuming saved selection; previous observations retain their timestamps.")
    else:
        if (args.output / "results.json").exists() and not args.overwrite:
            raise ValueError("Report exists. Choose --resume, --overwrite, or another --output.")
        console.print("[bold cyan]MC Name Finder[/bold cyan] · building word candidates")
        candidates = generate(
            list(dict.fromkeys(args.languages)),
            args.min_length,
            args.max_length,
            args.min_frequency,
            args.limit,
            args.words,
        )
        metadata = {
            "created_at_utc": utc_now(),
            "languages": args.languages,
            "min_length": args.min_length,
            "max_length": args.max_length,
            "min_frequency": args.min_frequency,
            "limit": args.limit,
            "source": "custom" if args.words else "wordfreq",
            "scan_complete": False,
        }
    console.print(f"{len(candidates):,} candidates · batch size 10 · {args.delay:g}s spacing")
    exit_code = 0
    try:
        if not args.dry_run:
            pending = [c for c in candidates if c.lookup_status == "UNKNOWN"]
            batches = [pending[i : i + 10] for i in range(0, len(pending), 10)]
            with MinecraftClient(bulk_delay=args.delay, notify=console.print) as client:
                for index, batch in enumerate(track(batches, description="Checking profiles"), 1):
                    taken = client.lookup([c.name for c in batch])
                    checked_at = utc_now()
                    for candidate in batch:
                        candidate.lookup_status = (
                            "TAKEN" if candidate.name in taken else "UNREGISTERED"
                        )
                        candidate.lookup_checked_at_utc = checked_at
                    if index % 10 == 0:
                        checkpoint(args.output, candidates, metadata)
            metadata["scan_complete"] = True
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Saving completed observations.[/yellow]")
        exit_code = 130
    except ApiError as error:
        console.print(f"[red]{error}[/red]")
        exit_code = 1
    finally:
        export_report(args.output, candidates, metadata)
        summary(candidates, args.output)
    return exit_code


def confirm(args) -> int:
    provider = AccountToken(args.account, notify=console.print) if args.account else None
    if not provider:
        load_dotenv(args.env_file, override=False)
        token = os.getenv("MC_ACCESS_TOKEN", "").strip()
        if not token or token.startswith("Bearer "):
            raise ValueError("Set MC_ACCESS_TOKEN in .env, or use --account after Microsoft login.")
    candidates, metadata = load_report(args.output)
    if args.names:
        requested = {name.lower() for name in args.names}
        known = {c.name for c in candidates}
        if requested - known:
            raise ValueError("Every --names value must exist in the saved report.")
        selected = [c for c in rank(candidates) if c.name in requested]
        if any(len(c.name) < 3 for c in selected):
            raise ValueError("Names must be at least 3 characters for availability checks.")
    else:
        selected = [c for c in rank(candidates) if c.lookup_status == "UNREGISTERED"]
    selected = [c for c in selected if args.refresh or c.exact_status == "NOT_CHECKED"]
    if not args.names:
        selected = selected[: args.top]
    console.print(f"Confirming {len(selected)} names · {args.delay:g}s spacing · read-only")
    exit_code = 0
    try:
        with (
            profile_lock(provider.identity["id"]) if provider else nullcontext(),
            MinecraftClient(exact_delay=args.delay, notify=console.print) as client,
        ):
            if provider:
                provider.profile(client)
            for candidate in track(selected, description="Confirming availability"):
                candidate.exact_status = (
                    provider.call(client.availability, candidate.name)
                    if provider
                    else client.availability(candidate.name, token)
                )
                candidate.exact_checked_at_utc = utc_now()
                console.print(f"{candidate.name:16} {candidate.exact_status}", markup=False)
                checkpoint(args.output, candidates, metadata)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Saving completed confirmations.[/yellow]")
        exit_code = 130
    except (ApiError, AuthError) as error:
        console.print(str(error), style="red", markup=False)
        exit_code = 1
    finally:
        export_report(args.output, candidates, metadata)
        summary(candidates, args.output)
    return exit_code


def connected_account(args) -> int:
    if args.command == "auth-setup":
        setup_helper(console.print)
        console.print("Microsoft login helper ready. Run login to connect your account.")
        return 0
    if args.command == "login":
        profile = login(args.account, notify=console.print, open_browser=not args.no_browser)
        console.print(f"Connected: {profile['name']} · alias: {args.account}", markup=False)
        console.print(f"Name change allowed: {profile['nameChangeAllowed']}")
        return 0
    if args.command == "logout":
        logout(args.account)
        console.print("Local account credentials removed. Microsoft sessions were not revoked.")
        return 0
    provider = AccountToken(args.account, notify=console.print)
    with (
        profile_lock(provider.identity["id"]),
        MinecraftClient(
            exact_delay=getattr(args, "interval", 16),
            notify=console.print,
        ) as client,
    ):
        if args.command == "account":
            profile = provider.profile(client)
            eligibility = provider.call(client.eligibility)
            console.print(
                f"Minecraft profile: {profile['name']} · alias: {args.account}", markup=False
            )
            console.print(f"UUID: {profile['id']}")
            console.print(f"Name change allowed: {eligibility['nameChangeAllowed']}")
            state_path = provider.directory / "watch.json"
            if state_path.exists():
                state = json.loads(state_path.read_text())
                if state.get("status") in {"CLAIMING", "UNCERTAIN", "UNVERIFIED"}:
                    state["status"] = (
                        "SUCCESS"
                        if profile["name"].lower() == state["target"].lower()
                        else "RESOLVED"
                    )
                    state["reconciled_at_utc"] = utc_now()
                    state["current_name"] = profile["name"]
                    atomic_write(state_path, json.dumps(state, indent=2) + "\n")
                    console.print(f"Previous change outcome reconciled: {state['status']}")
            return 0
        return run_watch(
            args.name,
            provider,
            client,
            provider.directory / "watch.json",
            claim=args.claim,
            expected_profile=args.expected_profile,
            start_at=args.start_at,
            interval=args.interval,
            max_minutes=args.max_minutes,
            notify=console.print,
        )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "scan":
            return scan(args)
        if args.command == "confirm":
            return confirm(args)
        return connected_account(args)
    except KeyboardInterrupt:
        console.print("\nStopped.")
        return 130
    except Timeout:
        console.print("This account or authentication helper is already in use by another process.")
        return 1
    except subprocess.SubprocessError:
        console.print("Local authentication helper failed; check Node.js/npm and retry login.")
        return 1
    except (OSError, ValueError, TypeError, KeyError, ApiError, AuthError) as error:
        # Paths and response contents can be attacker-controlled. Keep errors literal.
        console.print(f"Error: {error}", style="red", markup=False)
        return 1
