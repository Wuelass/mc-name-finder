from unittest.mock import Mock

import pytest
import requests

from mc_name_finder.api import (
    ApiError,
    ClaimRejected,
    ClaimUncertain,
    MinecraftClient,
    TokenRejected,
    valid_username,
)

UUID = "0123456789abcdef0123456789abcdef"


def client_response(code=200, payload=None):
    response = Mock(status_code=code, headers={})
    response.json.return_value = payload
    session = Mock()
    session.request.return_value = response
    return MinecraftClient(session=session), session


def test_account_profile_schema_and_eligibility():
    client, session = client_response(payload={"id": UUID, "name": "Player"})
    assert client.profile("secret") == {"id": UUID, "name": "Player"}
    session.request.return_value.json.return_value = {"nameChangeAllowed": False}
    assert client.eligibility("secret")["nameChangeAllowed"] is False


@pytest.mark.parametrize(
    "payload", [None, {}, {"id": "../bad", "name": "Name"}, {"id": UUID, "name": "has space"}]
)
def test_profile_fails_closed(payload):
    client, _ = client_response(payload=payload)
    with pytest.raises(ApiError):
        client.profile("secret")


@pytest.mark.parametrize("payload", [{}, {"nameChangeAllowed": "true"}, None])
def test_eligibility_requires_boolean(payload):
    client, _ = client_response(payload=payload)
    with pytest.raises(ApiError):
        client.eligibility("secret")


@pytest.mark.parametrize("name", ["ab", "a/b", "été", "x" * 17, "a b"])
def test_target_name_validation(name):
    with pytest.raises(ValueError):
        valid_username(name)


def test_target_supports_digits_underscores_and_case():
    assert valid_username("Ab_9") == "Ab_9"


@pytest.mark.parametrize("code", [200, 204])
def test_put_success_is_one_attempt_and_does_not_require_json(code):
    client, session = client_response(code)
    assert client.change_name("NewName", "secret") is None
    assert session.request.call_count == 1
    assert session.request.call_args.args[0] == "PUT"
    assert session.request.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("code", [400, 401, 403, 409, 429])
def test_put_refusal_is_not_retried(code):
    client, session = client_response(code)
    with pytest.raises(ClaimRejected):
        client.change_name("NewName", "secret")
    assert session.request.call_count == 1


@pytest.mark.parametrize("code", [302, 500, 503])
def test_unexpected_put_response_is_uncertain(code):
    client, session = client_response(code)
    with pytest.raises(ClaimUncertain):
        client.change_name("NewName", "secret")
    assert session.request.call_count == 1


def test_write_network_errors_are_redacted_not_retried():
    client, session = client_response()
    session.request.side_effect = requests.Timeout("secret")
    with pytest.raises(ClaimUncertain) as error:
        client.change_name("NewName", "secret")
    assert session.request.call_count == 1 and "secret" not in str(error.value)


def test_read_401_is_refreshable():
    client, session = client_response(401)
    with pytest.raises(TokenRejected):
        client.profile("secret")
    assert session.request.call_count == 1
