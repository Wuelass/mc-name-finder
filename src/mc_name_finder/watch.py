"""Single-target polling with explicit claim opt-in and account-identity pinning."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .api import ApiError, ClaimRejected, ClaimUncertain, valid_username
from .storage import atomic_write, utc_now


def parse_start(value: str) -> datetime:
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Use ISO 8601 for --start-at, e.g. 2026-10-15T23:11:46+02:00.") from None
    if date.tzinfo is None:
        raise ValueError("--start-at needs an explicit timezone, such as +02:00 or Z.")
    return date.astimezone(timezone.utc)


def run_watch(
    name: str,
    provider,
    client,
    state_path: Path,
    *,
    claim: bool = False,
    expected_profile: str | None = None,
    start_at: datetime | None = None,
    interval: float = 16,
    max_minutes: float | None = None,
    notify=lambda message: None,
    sleep=time.sleep,
    monotonic=time.monotonic,
    now=time.time,
) -> int:
    valid_username(name)
    profile = provider.profile(client)
    if (
        expected_profile
        and profile["name"].lower() != name.lower()
        and profile["name"].lower() != expected_profile.lower()
    ):
        raise ApiError("Current Minecraft name does not match --expected-profile; refusing to arm.")
    previous = None
    if state_path.exists():
        previous = json.loads(state_path.read_text())
        if not isinstance(previous, dict):
            raise ValueError("Invalid saved watcher state.")
    state = {
        "target": name,
        "profile_id": profile["id"],
        "initial_name": profile["name"],
        "claim_enabled": claim,
        "started_at_utc": utc_now(),
        "status": "PRECHECK",
    }

    def save(status, **fields):
        state.update(status=status, updated_at_utc=utc_now(), **fields)
        atomic_write(state_path, json.dumps(state, indent=2) + "\n")

    if profile["name"].lower() == name.lower():
        save("SUCCESS", current_name=profile["name"])
        notify(f"Your account already has the name {profile['name']}. Nothing to change.")
        return 0
    if previous and previous.get("status") in {"CLAIMING", "UNCERTAIN", "UNVERIFIED"}:
        raise ApiError(
            "A previous change has an unresolved outcome. Check Minecraft.net, then run "
            "account to reconcile it before restarting watch."
        )
    if claim and not provider.call(client.eligibility)["nameChangeAllowed"]:
        save("INELIGIBLE")
        raise ApiError(
            "Your account cannot change its name yet. Wait for the name-change cooldown."
        )
    notify(
        f"Account: {profile['name']} · target: {name} · automatic claim: {'ON' if claim else 'OFF'}"
    )
    notify("Keep this process and computer running. Ctrl+C stops it.")
    try:
        if start_at:
            save("WAITING", start_at_utc=start_at.isoformat())
            notify(f"Waiting until {start_at.isoformat()} (UTC).")
            while (remaining := start_at.timestamp() - now()) > 0:
                sleep(min(30, remaining))
        # Duration counts polling time, not the wait before --start-at.
        deadline = None if max_minutes is None else monotonic() + max_minutes * 60
        while deadline is None or monotonic() < deadline:
            # Refresh early and verify UUID/current name before each availability check.
            profile = provider.profile(client)
            if profile["name"].lower() == name.lower():
                save("SUCCESS", current_name=profile["name"])
                notify(f"SUCCESS: your Minecraft name is {profile['name']}.")
                return 0
            if profile["name"].lower() != state["initial_name"].lower():
                save("ACCOUNT_CHANGED")
                raise ApiError("Your profile name changed outside this watcher; stopping.")
            status = provider.call(client.availability, name)
            save("WATCHING", availability=status, checked_at_utc=utc_now())
            notify(f"[{utc_now()}] {name}: {status}")
            if status == "NOT_ALLOWED":
                save("NOT_ALLOWED")
                notify("Minecraft disallows this name. Monitoring stopped.")
                return 1
            if status == "AVAILABLE":
                if not claim:
                    save("AVAILABLE")
                    notify("Name available. Monitor-only mode: no account change was sent.")
                    return 0
                token = provider.get()
                current = client.profile(token)
                if (
                    current["id"].lower() != state["profile_id"].lower()
                    or current["name"].lower() != state["initial_name"].lower()
                ):
                    save("ACCOUNT_CHANGED")
                    raise ApiError(
                        "Account identity or name changed before claim; refusing to act."
                    )
                if not client.eligibility(token)["nameChangeAllowed"]:
                    save("INELIGIBLE")
                    raise ApiError("Account is no longer eligible for a name change; stopping.")
                save("CLAIMING")  # durable before the write, to survive a process crash
                notify(f"Attempting to change your name to {name}…")
                uncertain = False
                try:
                    client.change_name(name, token)
                except ClaimRejected:
                    save("REJECTED")
                    raise
                except ClaimUncertain:
                    uncertain = True
                # Never infer success just from the write response, and never resend blindly.
                try:
                    current = provider.profile(client)
                except ApiError:
                    save("UNCERTAIN")
                    raise ClaimUncertain(
                        "Could not verify the outcome. Check your Minecraft profile."
                    ) from None
                if current["name"].lower() == name.lower():
                    save("SUCCESS", current_name=current["name"])
                    notify(f"SUCCESS: your Minecraft name is now {current['name']}.")
                    return 0
                save("UNCERTAIN" if uncertain else "UNVERIFIED")
                raise ClaimUncertain(
                    "Your profile does not yet confirm this name. No second write was sent."
                )
            if deadline is not None:
                sleep(min(interval, max(0, deadline - monotonic())))
            else:
                sleep(interval)
        save("TIMED_OUT")
        notify("Monitoring duration reached. No name change was made.")
        return 0
    except KeyboardInterrupt:
        if state["status"] == "CLAIMING":
            save("UNCERTAIN")
        else:
            save("STOPPED")
        notify("Stopped. Latest status saved; no further requests will be sent.")
        return 130
    except Exception:
        # Preserve durable CLAIMING/UNCERTAIN markers for account reconciliation.
        if state["status"] == "CLAIMING":
            save("UNCERTAIN")
        elif state["status"] not in {
            "UNCERTAIN",
            "INELIGIBLE",
            "REJECTED",
            "UNVERIFIED",
            "ACCOUNT_CHANGED",
        }:
            save("ERROR")
        raise
