import json
import time
from unittest.mock import Mock

import pytest
from filelock import Timeout

from mc_name_finder import auth
from mc_name_finder.api import TokenRejected

UUID = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def saved_account(tmp_path, monkeypatch):
    monkeypatch.setenv("MC_NAME_FINDER_HOME", str(tmp_path))
    directory = auth.account_directory("main")
    (directory / "account.json").write_text(json.dumps({"id": UUID, "name": "OldName"}))
    return directory


def mock_profile_client(monkeypatch, profile_id=UUID):
    client = Mock()
    client.profile.return_value = {"id": profile_id, "name": "OldName"}
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(auth, "MinecraftClient", Mock(return_value=client))
    return client


def test_provider_reuses_token_and_refreshes_once(saved_account, monkeypatch):
    bridge = Mock(return_value=("secret", time.time() + 3600))
    monkeypatch.setattr(auth, "bridge_token", bridge)
    mock_profile_client(monkeypatch)
    provider = auth.AccountToken("main")
    assert provider.get() == provider.get() == "secret"
    assert bridge.call_count == 1
    read = Mock(side_effect=[TokenRejected("expired"), "AVAILABLE"])
    assert provider.call(read, "Name") == "AVAILABLE"
    assert bridge.call_count == 2 and read.call_count == 2
    assert bridge.call_args.kwargs["refresh"] is True


def test_refreshed_wrong_identity_is_rejected(saved_account, monkeypatch):
    monkeypatch.setattr(auth, "bridge_token", Mock(return_value=("secret", time.time() + 3600)))
    mock_profile_client(monkeypatch, "f" * 32)
    provider = auth.AccountToken("main")
    with pytest.raises(auth.AuthError, match="another profile"):
        provider.get()
    assert provider.token == ""


def test_profile_binding_and_missing_account(saved_account):
    provider = auth.AccountToken("main")
    provider.token, provider.expires = "secret", time.time() + 3600
    client = Mock()
    client.profile.return_value = {"id": "f" * 32, "name": "Other"}
    with pytest.raises(auth.AuthError, match="differs"):
        provider.profile(client)
    with pytest.raises(auth.AuthError, match="login"):
        auth.AccountToken("missing")


@pytest.mark.parametrize("alias", ["../escape", "a/b", "", "x" * 41])
def test_account_alias_cannot_escape_directory(alias):
    with pytest.raises(ValueError):
        auth.account_directory(alias)


def test_profile_lock_prevents_two_watchers_for_same_uuid(saved_account):
    with auth.profile_lock(UUID):
        with pytest.raises(Timeout):
            with auth.profile_lock(UUID):
                pytest.fail("Second watcher obtained the lock")


def test_logout_removes_local_tokens_identity_but_retains_watch_state(saved_account):
    tokens = saved_account / "tokens"
    tokens.mkdir()
    (tokens / "live.json").write_text("secret")
    (saved_account / "watch.json").write_text("{}")
    auth.logout("main")
    assert not tokens.exists() and not (saved_account / "account.json").exists()
    assert (saved_account / "watch.json").exists()
