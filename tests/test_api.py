from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import Mock

import pytest
import requests

from mc_name_finder.api import ApiError, MinecraftClient, retry_after


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def response(code=200, payload=None, headers=None):
    result = Mock(status_code=code, headers=headers or {})
    result.json.return_value = payload
    return result


def client_with(*responses):
    session = Mock()
    session.request.side_effect = responses
    clock = FakeClock()
    client = MinecraftClient(session=session, clock=lambda: clock.now, sleep=clock.sleep)
    return client, session, clock


def test_bulk_is_case_insensitive_and_does_not_send_token():
    client, session, _ = client_with(response(payload=[{"name": "Fox", "id": "uuid"}]))
    assert client.lookup(["fox", "owl"]) == {"fox"}
    kwargs = session.request.call_args.kwargs
    assert "headers" not in kwargs
    assert kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "payload", [None, {}, [{"name": "fox"}], [{"name": "other", "id": "uuid"}]]
)
def test_invalid_bulk_schema_never_becomes_unregistered(payload):
    client, _, _ = client_with(response(payload=payload))
    with pytest.raises(ApiError):
        client.lookup(["fox"])


def test_bulk_size_validation():
    client, session, _ = client_with()
    for names in ([], ["a"] * 11):
        with pytest.raises(ValueError):
            client.lookup(names)
    session.request.assert_not_called()


@pytest.mark.parametrize("status", ["AVAILABLE", "DUPLICATE", "NOT_ALLOWED"])
def test_exact_known_statuses(status):
    client, session, _ = client_with(response(payload={"status": status}))
    assert client.availability("fox", "test-secret") == status
    assert session.request.call_args.kwargs["headers"]["Authorization"] == "Bearer test-secret"


@pytest.mark.parametrize("payload", [{}, {"status": "NEW_STATUS"}, []])
def test_exact_unknown_status_fails_closed(payload):
    client, _, _ = client_with(response(payload=payload))
    with pytest.raises(ApiError):
        client.availability("fox", "test-secret")


def test_retry_after_then_success_and_spacing():
    client, session, clock = client_with(
        response(429, headers={"Retry-After": "45"}), response(payload=[]), response(payload=[])
    )
    assert client.lookup(["fox"]) == set()
    client.lookup(["owl"])
    assert session.request.call_count == 3
    assert 45 in clock.waits and 1 in clock.waits


def test_confirmation_request_spacing():
    client, _, clock = client_with(*[response(payload={"status": "AVAILABLE"}) for _ in range(2)])
    client.availability("fox", "secret")
    client.availability("owl", "secret")
    assert clock.now == 16


@pytest.mark.parametrize("code", [401, 403])
def test_authentication_error_is_not_retried_or_leaked(code):
    client, session, _ = client_with(response(code, payload={"token": "test-secret"}))
    with pytest.raises(ApiError) as error:
        client.availability("fox", "test-secret")
    assert "test-secret" not in str(error.value)
    assert session.request.call_count == 1


def test_retry_budget_is_bounded():
    client, session, _ = client_with(*[response(503) for _ in range(4)])
    with pytest.raises(ApiError):
        client.lookup(["fox"])
    assert session.request.call_count == 4


def test_network_exception_is_redacted():
    client, _, _ = client_with(*[requests.ConnectionError("test-secret") for _ in range(4)])
    with pytest.raises(ApiError) as error:
        client.availability("fox", "test-secret")
    assert "test-secret" not in str(error.value)


def test_invalid_json_and_redirect_fail_closed():
    broken = response()
    broken.json.side_effect = ValueError("raw-sensitive-body")
    client, _, _ = client_with(broken)
    with pytest.raises(ApiError, match="Malformed JSON"):
        client.lookup(["fox"])
    client, _, _ = client_with(response(302))
    with pytest.raises(ApiError, match="HTTP 302"):
        client.lookup(["fox"])


def test_retry_after_numeric_date_and_fallback():
    assert retry_after("42", 30) == 42
    assert retry_after("-5", 30) == 0
    assert retry_after("garbage", 30) == 30
    assert retry_after("nan", 30) == 30
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=60), usegmt=True)
    assert 58 <= retry_after(future, 30) <= 60
