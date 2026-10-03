"""Public CLI; discovery and authenticated confirmation are deliberately separate."""

import argparse
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import track
from rich.table import Table

from . import __version__
from .api import ApiError, MinecraftClient
from .storage import checkpoint, export_report, load_report, utc_now
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
    confirm.add_argument("--delay", type=bounded_float(16), default=16.0)
    confirm.add_argument(
        "--refresh", action="store_true", help="Recheck previously confirmed names"
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
    load_dotenv(args.env_file, override=False)
    token = os.getenv("MC_ACCESS_TOKEN", "").strip()
    if not token or token.startswith("Bearer "):
        raise ValueError("Set MC_ACCESS_TOKEN in .env to a Minecraft token, without 'Bearer '.")
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
        with MinecraftClient(exact_delay=args.delay, notify=console.print) as client:
            for candidate in track(selected, description="Confirming availability"):
                candidate.exact_status = client.availability(candidate.name, token)
                candidate.exact_checked_at_utc = utc_now()
                console.print(f"{candidate.name:16} {candidate.exact_status}", markup=False)
                checkpoint(args.output, candidates, metadata)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Saving completed confirmations.[/yellow]")
        exit_code = 130
    except ApiError as error:
        console.print(f"[red]{error}[/red]")
        exit_code = 1
    finally:
        export_report(args.output, candidates, metadata)
        summary(candidates, args.output)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return scan(args) if args.command == "scan" else confirm(args)
    except (OSError, ValueError, TypeError, KeyError) as error:
        # Paths and response contents can be attacker-controlled. Keep errors literal.
        console.print(f"Error: {error}", style="red", markup=False)
        return 1
