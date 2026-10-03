import csv
import json
from unittest.mock import Mock

import pytest

from mc_name_finder.api import ApiError
from mc_name_finder.cli import main
from mc_name_finder.storage import export_report, load_report
from mc_name_finder.words import Candidate


@pytest.fixture
def fake_api(monkeypatch):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.lookup.return_value = set()
    client.availability.return_value = "AVAILABLE"
    monkeypatch.setattr("mc_name_finder.cli.MinecraftClient", Mock(return_value=client))
    return client


def seed_report(path, count=2):
    rows = [
        Candidate(name, lookup_status="UNREGISTERED", lookup_checked_at_utc="old-time")
        for name in ["fox", "owl"][:count]
    ]
    export_report(path, rows, {"source": "custom"})


def test_dry_run_and_resume(tmp_path, fake_api):
    words = tmp_path / "words.txt"
    words.write_text("fox\nowl\nox\n", encoding="utf-8")
    output = tmp_path / "out"
    assert main(["scan", "--words", str(words), "--output", str(output), "--dry-run"]) == 0
    fake_api.lookup.assert_not_called()
    assert main(["scan", "--resume", "--output", str(output)]) == 0
    rows, metadata = load_report(output)
    assert metadata["scan_complete"] is True
    assert {c.name for c in rows if c.lookup_status == "UNREGISTERED"} == {"fox", "owl"}
    assert next(c for c in rows if c.name == "ox").lookup_checked_at_utc is None
    assert main(["scan", "--resume", "--output", str(output)]) == 0
    assert fake_api.lookup.call_count == 1
    assert main(["scan", "--output", str(output)]) == 1


def test_partial_failure_and_resume_preserve_observations(tmp_path, fake_api):
    output = tmp_path / "out"
    words = tmp_path / "words.txt"
    names = [f"word{chr(97 + i)}" for i in range(11)]
    words.write_text("\n".join(names), encoding="utf-8")
    fake_api.lookup.side_effect = [set(), ApiError("service unavailable")]
    assert main(["scan", "--words", str(words), "--output", str(output)]) == 1
    rows, _ = load_report(output)
    assert sum(c.lookup_status == "UNREGISTERED" for c in rows) == 10
    first_time = rows[0].lookup_checked_at_utc
    fake_api.lookup.side_effect = None
    assert main(["scan", "--resume", "--output", str(output)]) == 0
    rows, _ = load_report(output)
    assert rows[0].lookup_checked_at_utc == first_time
    assert all(c.lookup_status == "UNREGISTERED" for c in rows)
    assert fake_api.lookup.call_args.args[0] == [names[-1]]


def test_interrupt_saves_results(tmp_path, fake_api):
    words = tmp_path / "words.txt"
    words.write_text("fox", encoding="utf-8")
    output = tmp_path / "out"
    fake_api.lookup.side_effect = KeyboardInterrupt
    assert main(["scan", "--words", str(words), "--output", str(output)]) == 130
    rows, _ = load_report(output)
    assert rows[0].lookup_status == "UNKNOWN"


def test_confirm_token_isolation_and_skip_refresh(tmp_path, fake_api, monkeypatch):
    output = tmp_path / "out"
    seed_report(output)
    env = tmp_path / ".env"
    env.write_text("MC_ACCESS_TOKEN=file-secret", encoding="utf-8")
    monkeypatch.setenv("MC_ACCESS_TOKEN", "environment-secret")
    args = ["confirm", "--output", str(output), "--env-file", str(env), "--top", "1"]
    assert main(args) == 0
    assert fake_api.availability.call_args.args == ("fox", "environment-secret")
    rows, _ = load_report(output)
    assert rows[0].lookup_checked_at_utc == "old-time"
    assert rows[0].exact_checked_at_utc is not None
    assert rows[1].exact_status == "NOT_CHECKED"
    assert main(args + ["--names", "FOX"]) == 0
    assert fake_api.availability.call_count == 1
    assert main(args + ["--names", "fox", "--refresh"]) == 0
    assert fake_api.availability.call_count == 2
    for path in output.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "environment-secret" not in text and "file-secret" not in text


def test_missing_token_and_unknown_names_fail_before_requests(tmp_path, fake_api, monkeypatch):
    output = tmp_path / "out"
    seed_report(output)
    monkeypatch.delenv("MC_ACCESS_TOKEN", raising=False)
    env = tmp_path / "empty.env"
    env.write_text("MC_ACCESS_TOKEN=", encoding="utf-8")
    args = ["confirm", "--output", str(output), "--env-file", str(env)]
    assert main(args) == 1
    monkeypatch.setenv("MC_ACCESS_TOKEN", "secret")
    assert main(args + ["--names", "unknown"]) == 1
    fake_api.availability.assert_not_called()


def test_confirmation_failure_preserves_prior_and_exports(tmp_path, fake_api, monkeypatch):
    output = tmp_path / "out"
    seed_report(output)
    monkeypatch.setenv("MC_ACCESS_TOKEN", "secret")
    fake_api.availability.side_effect = ["AVAILABLE", ApiError("expired")]
    assert main(["confirm", "--output", str(output)]) == 1
    rows, _ = load_report(output)
    assert rows[0].exact_status == "AVAILABLE"
    assert rows[1].exact_status == "NOT_CHECKED"


@pytest.mark.parametrize(
    "args",
    [
        ["scan", "--delay", "0.1"],
        ["confirm", "--delay", "15"],
        ["scan", "--delay", "nan"],
        ["scan", "--limit", "0"],
    ],
)
def test_invalid_pacing_and_limits(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_export_roundtrip_and_status_separation(tmp_path):
    rows = [
        Candidate(
            "fox",
            originals=["fox"],
            lookup_status="TAKEN",
            exact_status="AVAILABLE",
            lookup_checked_at_utc="old",
            exact_checked_at_utc="new",
        )
    ]
    export_report(tmp_path, rows, {"source": "custom"})
    restored, _ = load_report(tmp_path)
    assert restored == rows
    assert (tmp_path / "unregistered_3_letters.txt").read_text() == ""
    assert (tmp_path / "available_exact_3_letters.txt").read_text() == "fox\n"
    with (tmp_path / "results.csv").open(encoding="utf-8-sig", newline="") as f:
        report = list(csv.DictReader(f))
    assert report[0]["lookup_checked_at_utc"] == "old"
    assert report[0]["exact_checked_at_utc"] == "new"


def test_edited_report_names_cannot_inject_urls(tmp_path):
    seed_report(tmp_path)
    path = tmp_path / "results.json"
    data = json.loads(path.read_text())
    data["candidates"][0]["name"] = "../../secret"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="invalid candidate"):
        load_report(tmp_path)


def test_login_cli_displays_profile_without_exposing_token(monkeypatch, capsys):
    signin = Mock(return_value={"id": "0" * 32, "name": "MyPlayer", "nameChangeAllowed": True})
    monkeypatch.setattr("mc_name_finder.cli.login", signin)
    assert main(["login", "--account", "main", "--no-browser"]) == 0
    assert signin.call_args.kwargs["open_browser"] is False
    assert signin.call_args.args == ("main",)
    assert "MyPlayer" in capsys.readouterr().out


def test_watch_cli_routes_explicit_claim_and_schedule(monkeypatch, tmp_path, fake_api):
    from contextlib import nullcontext

    provider = Mock()
    provider.identity = {"id": "0" * 32, "name": "OldName"}
    provider.directory = tmp_path
    monkeypatch.setattr("mc_name_finder.cli.AccountToken", Mock(return_value=provider))
    monkeypatch.setattr("mc_name_finder.cli.profile_lock", lambda uuid: nullcontext())
    engine = Mock(return_value=0)
    monkeypatch.setattr("mc_name_finder.cli.run_watch", engine)
    assert (
        main(
            [
                "watch",
                "Ab_9",
                "--claim",
                "--expected-profile",
                "OldName",
                "--start-at",
                "2026-10-15T23:11:46+02:00",
                "--max-minutes",
                "10",
            ]
        )
        == 0
    )
    assert engine.call_args.args[0] == "Ab_9"
    assert engine.call_args.kwargs["claim"] is True
    assert engine.call_args.kwargs["start_at"].hour == 21
    assert engine.call_args.kwargs["expected_profile"] == "OldName"


def test_account_reconciles_uncertain_outcome_without_writing(monkeypatch, tmp_path, fake_api):
    from contextlib import nullcontext

    provider = Mock()
    provider.identity = {"id": "0" * 32, "name": "OldName"}
    provider.directory = tmp_path
    provider.profile.return_value = {"id": "0" * 32, "name": "NewName"}
    provider.call.return_value = {"nameChangeAllowed": False}
    monkeypatch.setattr("mc_name_finder.cli.AccountToken", Mock(return_value=provider))
    monkeypatch.setattr("mc_name_finder.cli.profile_lock", lambda uuid: nullcontext())
    (tmp_path / "watch.json").write_text(json.dumps({"status": "UNCERTAIN", "target": "NewName"}))
    assert main(["account"]) == 0
    assert json.loads((tmp_path / "watch.json").read_text())["status"] == "SUCCESS"
    fake_api.change_name.assert_not_called()


@pytest.mark.parametrize(
    "args",
    [
        ["watch", "ab"],
        ["watch", "abc", "--interval", "1"],
        ["watch", "abc", "--start-at", "2026-10-15T23:11:46"],
    ],
)
def test_watch_rejects_invalid_targets_pacing_and_naive_schedule(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
