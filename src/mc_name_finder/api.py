"""Small Minecraft Services client with bounded retries and fail-closed parsing."""

import math
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

BASE_URL = "https://api.minecraftservices.com"
BULK_URL = f"{BASE_URL}/minecraft/profile/lookup/bulk/byname"
EXACT_URL = f"{BASE_URL}/minecraft/profile/name/{{}}/available"


class ApiError(Exception):
    """Safe user-facing error; never includes response bodies or credentials."""


class TokenRejected(ApiError):
    """A read request rejected the Minecraft token (HTTP 401)."""


class ClaimRejected(ApiError):
    """The server explicitly refused the requested name change."""


class ClaimUncertain(ApiError):
    """The name-change outcome needs reconciliation; never blindly retry PUT."""


def valid_username(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]{3,16}", name):
        raise ValueError("A target name must use 3–16 ASCII letters, digits or underscores.")
    return name


def parse_profile(payload: object) -> dict:
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("id"), str)
        or not re.fullmatch(r"[0-9a-fA-F]{32}", payload["id"])
        or not isinstance(payload.get("name"), str)
        or not re.fullmatch(r"[A-Za-z0-9_]{1,16}", payload["name"])
    ):
        raise ApiError("Unexpected Minecraft profile response; no account identity inferred.")
    return {"id": payload["id"], "name": payload["name"]}


def retry_after(value: str | None, fallback: float) -> float:
    try:
        seconds = float(value or "")
        if math.isfinite(seconds):
            return max(0.0, seconds)
    except ValueError:
        pass
    try:
        date = parsedate_to_datetime(value or "")
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return fallback


class MinecraftClient:
    def __init__(
        self,
        bulk_delay: float = 1.0,
        exact_delay: float = 16.0,
        session: requests.Session | None = None,
        sleep: Callable = time.sleep,
        clock: Callable = time.monotonic,
        notify: Callable = lambda message: None,
    ):
        self.session = session or requests.Session()
        self.bulk_delay = bulk_delay
        self.exact_delay = exact_delay
        self.sleep = sleep
        self.clock = clock
        self.notify = notify
        self.last_request: dict[str, float] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def _request(self, method: str, url: str, kind: str, **kwargs):
        interval = self.exact_delay if kind == "exact" else self.bulk_delay
        for attempt in range(4):
            if kind in self.last_request:
                self.sleep(max(0.0, interval - (self.clock() - self.last_request[kind])))
            self.last_request[kind] = self.clock()
            try:
                response = self.session.request(
                    method, url, timeout=(5, 20), allow_redirects=False, **kwargs
                )
            except requests.RequestException:
                if attempt == 3:
                    raise ApiError("Network request failed after 4 attempts.") from None
                self.sleep(2 ** (attempt + 1))
                continue
            if response.status_code == 401 and kind != "bulk":
                raise TokenRejected(
                    "Minecraft token rejected or expired; log in again or refresh it."
                )
            if response.status_code in (401, 403):
                message = (
                    "Minecraft token rejected or expired; update MC_ACCESS_TOKEN."
                    if kind != "bulk"
                    else "Public lookup refused (401/403); try again later."
                )
                raise ApiError(message)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == 3:
                    raise ApiError(f"HTTP {response.status_code}: retry budget exhausted.")
                wait = retry_after(response.headers.get("Retry-After"), 30.0 * 2**attempt)
                self.notify(f"HTTP {response.status_code}; retrying in {wait:.0f}s.")
                self.sleep(wait)
                continue
            if response.status_code != 200:
                raise ApiError(f"Unexpected HTTP {response.status_code}; no result inferred.")
            try:
                return response.json()
            except ValueError:
                raise ApiError("Malformed JSON response; no result inferred.") from None
        raise ApiError("Request failed.")  # pragma: no cover

    def lookup(self, names: list[str]) -> set[str]:
        if not 1 <= len(names) <= 10:
            raise ValueError("Bulk lookup requires between 1 and 10 names.")
        payload = self._request("POST", BULK_URL, "bulk", json=names)
        if not isinstance(payload, list):
            raise ApiError("Unexpected bulk response schema; no result inferred.")
        found = set()
        requested = {name.lower() for name in names}
        for item in payload:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                or item["name"].lower() not in requested
            ):
                raise ApiError("Unexpected bulk profile; no result inferred.")
            found.add(item["name"].lower())
        return found

    def availability(self, name: str, token: str) -> str:
        valid_username(name)
        payload = self._request(
            "GET",
            EXACT_URL.format(name),
            "exact",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if not isinstance(payload, dict) or payload.get("status") not in {
            "AVAILABLE",
            "DUPLICATE",
            "NOT_ALLOWED",
        }:
            raise ApiError("Unexpected availability response; no result inferred.")
        return payload["status"]

    def profile(self, token: str) -> dict:
        return parse_profile(
            self._request(
                "GET",
                f"{BASE_URL}/minecraft/profile",
                "account",
                headers={"Authorization": f"Bearer {token}"},
            )
        )

    def eligibility(self, token: str) -> dict:
        payload = self._request(
            "GET",
            f"{BASE_URL}/minecraft/profile/namechange",
            "account",
            headers={"Authorization": f"Bearer {token}"},
        )
        if not isinstance(payload, dict) or type(payload.get("nameChangeAllowed")) is not bool:
            raise ApiError("Unexpected name-change eligibility response; refusing a change.")
        return payload

    def change_name(self, name: str, token: str) -> None:
        """One write attempt. Even a timeout may mean success; reads reconcile the result."""
        valid_username(name)
        try:
            response = self.session.request(
                "PUT",
                f"{BASE_URL}/minecraft/profile/name/{name}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=(5, 20),
                allow_redirects=False,
            )
        except requests.RequestException:
            raise ClaimUncertain(
                "Name-change response lost. Verify your profile before retrying."
            ) from None
        if response.status_code in (200, 204):
            return
        if response.status_code in (400, 401, 403, 409, 429):
            raise ClaimRejected(
                f"Name change refused (HTTP {response.status_code}); no automatic write retry."
            )
        raise ClaimUncertain(
            f"Unexpected name-change response (HTTP {response.status_code}); verify your profile."
        )
