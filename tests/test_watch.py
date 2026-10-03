import json
from datetime import datetime, timezone

import pytest

from mc_name_finder.api import ApiError, ClaimRejected, ClaimUncertain
from mc_name_finder.watch import parse_start, run_watch

UUID = "0123456789abcdef0123456789abcdef"


class Clock:
    def __init__(self):
        self.time = 0.0
        self.waits = []

    def sleep(self, seconds):
        self.time += seconds
        self.waits.append(seconds)


class Client:
    def __init__(self, statuses=None, eligible=True):
        self.name = "OldName"
        self.id = UUID
        self.statuses = iter(statuses or ["AVAILABLE"])
        self.eligible = eligible
        self.writes = 0
        self.write_error = None
        self.commit_on_error = False
        self.checks = 0

    def profile(self, token):
        return {"id": self.id, "name": self.name}

    def eligibility(self, token):
        return {"nameChangeAllowed": self.eligible}

    def availability(self, name, token):
        self.checks += 1
        value = next(self.statuses)
        if isinstance(value, BaseException):
            raise value
        return value

    def change_name(self, name, token):
        self.writes += 1
        if not self.write_error or self.commit_on_error:
            self.name = name
        if self.write_error:
            raise self.write_error


class Provider:
    def __init__(self, client):
        self.client = client

    def get(self):
        return "secret"

    def call(self, method, *args):
        return method(*args, self.get())

    def profile(self, client):
        profile = client.profile(self.get())
        if profile["id"] != UUID:
            raise ApiError("identity changed")
        return profile


def watch(client, tmp_path, clock=None, **kwargs):
    clock = clock or Clock()
    return run_watch(
        "NewName",
        Provider(client),
        client,
        tmp_path / "watch.json",
        sleep=clock.sleep,
        monotonic=lambda: clock.time,
        now=lambda: clock.time,
        **kwargs,
    )


def state(tmp_path):
    return json.loads((tmp_path / "watch.json").read_text())


def test_available_monitor_never_changes_account(tmp_path):
    client = Client()
    assert watch(client, tmp_path) == 0
    assert client.writes == 0
    assert state(tmp_path)["status"] == "AVAILABLE"


def test_wait_then_claim_once_and_confirm_success(tmp_path):
    client = Client(["DUPLICATE", "AVAILABLE"])
    clock = Clock()
    assert watch(client, tmp_path, clock, claim=True, expected_profile="OldName") == 0
    assert client.writes == 1 and client.name == "NewName"
    assert clock.waits == [16]
    assert state(tmp_path)["status"] == "SUCCESS"
    assert "secret" not in (tmp_path / "watch.json").read_text()
    # Re-running the exact same command is idempotent, including expected old name.
    assert watch(client, tmp_path, claim=True, expected_profile="OldName") == 0
    assert client.writes == 1


def test_ineligible_account_never_checks_or_writes(tmp_path):
    client = Client(eligible=False)
    with pytest.raises(ApiError, match="cooldown"):
        watch(client, tmp_path, claim=True)
    assert client.checks == client.writes == 0
    assert state(tmp_path)["status"] == "INELIGIBLE"


def test_wrong_expected_account_stops_before_api_checks(tmp_path):
    client = Client()
    with pytest.raises(ApiError, match="expected-profile"):
        watch(client, tmp_path, claim=True, expected_profile="AnotherName")
    assert client.checks == client.writes == 0


def test_disallowed_name_stops(tmp_path):
    client = Client(["NOT_ALLOWED"])
    assert watch(client, tmp_path, claim=True) == 1
    assert client.writes == 0
    assert state(tmp_path)["status"] == "NOT_ALLOWED"


def test_uncertain_write_can_be_reconciled_as_success(tmp_path):
    client = Client()
    client.write_error = ClaimUncertain("timeout")
    client.commit_on_error = True
    assert watch(client, tmp_path, claim=True) == 0
    assert client.writes == 1
    assert state(tmp_path)["status"] == "SUCCESS"


def test_uncertain_write_is_not_blindly_retried(tmp_path):
    client = Client()
    client.write_error = ClaimUncertain("timeout")
    with pytest.raises(ClaimUncertain):
        watch(client, tmp_path, claim=True)
    assert client.writes == 1
    assert state(tmp_path)["status"] == "UNCERTAIN"
    with pytest.raises(ApiError, match="unresolved"):
        watch(client, tmp_path, claim=True)
    assert client.writes == 1


def test_refused_claim_is_terminal(tmp_path):
    client = Client()
    client.write_error = ClaimRejected("HTTP 403")
    with pytest.raises(ClaimRejected):
        watch(client, tmp_path, claim=True)
    assert client.writes == 1 and state(tmp_path)["status"] == "REJECTED"


def test_schedule_waits_in_bounded_chunks(tmp_path):
    client = Client()
    clock = Clock()
    assert watch(client, tmp_path, clock, start_at=datetime.fromtimestamp(65, timezone.utc)) == 0
    assert clock.waits == [30, 30, 5]
    assert client.writes == 0


def test_deadline_limits_polling(tmp_path):
    client = Client(["DUPLICATE"] * 10)
    clock = Clock()
    assert watch(client, tmp_path, clock, max_minutes=0.5, claim=True) == 0
    assert clock.time == 30 and client.writes == 0 and client.checks == 2
    assert state(tmp_path)["status"] == "TIMED_OUT"


def test_interrupt_records_state_and_does_not_write(tmp_path):
    client = Client([KeyboardInterrupt()])
    assert watch(client, tmp_path, claim=True) == 130
    assert state(tmp_path)["status"] == "STOPPED" and client.writes == 0


def test_crash_during_claim_records_uncertainty(tmp_path, monkeypatch):
    client = Client()
    monkeypatch.setattr(
        client, "change_name", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())
    )
    assert watch(client, tmp_path, claim=True) == 130
    assert state(tmp_path)["status"] == "UNCERTAIN"


def test_identity_rechecked_before_put(tmp_path, monkeypatch):
    client = Client()

    def availability(*args):
        client.id = "f" * 32
        return "AVAILABLE"

    monkeypatch.setattr(client, "availability", availability)
    with pytest.raises(ApiError, match="identity"):
        watch(client, tmp_path, claim=True)
    assert client.writes == 0


@pytest.mark.parametrize("value", ["2026-10-15T23:12:46", "not-a-date"])
def test_start_requires_valid_explicit_timezone(value):
    with pytest.raises(ValueError):
        parse_start(value)


def test_start_converts_timezone():
    assert parse_start("2026-10-15T23:12:46+02:00").hour == 21
    assert parse_start("2026-10-15T21:12:46Z").hour == 21
