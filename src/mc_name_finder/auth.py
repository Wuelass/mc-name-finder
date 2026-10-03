"""Device-code login via a pinned PrismarineJS bridge; secrets stay in local caches."""

import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from filelock import FileLock

from .api import ApiError, MinecraftClient, TokenRejected
from .storage import atomic_write


class AuthError(Exception):
    """Redacted authentication or local setup error."""


def data_directory() -> Path:
    if override := os.getenv("MC_NAME_FINDER_HOME"):
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "MCNameFinder"
    return Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "mc-name-finder"


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise AuthError("Authentication directory must not be a symlink.")
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    elif created:
        # Restrict the new cache to the signed-in Windows user, including child files.
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True
        )
        sid = list(csv.reader(io.StringIO(identity.stdout)))[0][-1]
        if not re.fullmatch(r"S-1-[0-9-]+", sid):
            raise AuthError("Could not determine the Windows user SID.")
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise AuthError("Could not restrict Windows authentication-cache permissions.")


def account_directory(account: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", account):
        raise ValueError("Account alias must use 1–40 letters, digits, underscores or hyphens.")
    root = data_directory()
    private_directory(root)
    directory = root / "accounts" / account
    private_directory(directory)
    return directory


def setup_helper(notify=lambda message: None) -> Path:
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise AuthError(
            "Install Node.js 20+ (including npm), reopen your terminal, then run login."
        )
    version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True)
    if int(version.stdout.strip().lstrip("v").split(".")[0]) < 20:
        raise AuthError("Node.js 20 or newer is required for Microsoft login.")
    root = data_directory()
    private_directory(root)
    runtime = root / "auth-helper"
    private_directory(runtime)
    source = Path(__file__).parent / "node"
    with FileLock(str(root / "helper.lock"), timeout=0):
        changed = False
        for name in ("package.json", "package-lock.json", "bridge.cjs"):
            content = (source / name).read_bytes()
            target = runtime / name
            if not target.exists() or target.read_bytes() != content:
                target.write_bytes(content)
                changed |= name != "bridge.cjs"
        if changed or not (runtime / "node_modules/prismarine-auth/package.json").exists():
            notify("Installing the Microsoft authentication helper (first run only)…")
            command = [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
            if os.name == "nt":
                # Invoke npm through Node, avoiding .cmd shell quoting and spaces in paths.
                npm_cli = Path(npm).resolve().parent / "node_modules/npm/bin/npm-cli.js"
                if not npm_cli.exists():
                    raise AuthError(
                        "npm-cli.js not found. Reinstall the official Node.js LTS build."
                    )
                command = [node, str(npm_cli), *command[1:]]
            result = subprocess.run(command, cwd=runtime, capture_output=True, timeout=180)
            if result.returncode:
                raise AuthError(
                    "Authentication helper installation failed. Check npm/network access."
                )
    return runtime


def bridge_token(
    directory: Path,
    *,
    interactive: bool = False,
    refresh: bool = False,
    open_browser: bool = True,
    notify=lambda message: None,
) -> tuple[str, float]:
    runtime = setup_helper(notify)
    cache = directory / "tokens"
    private_directory(cache)
    environment = {**os.environ, "DEBUG": ""}
    process = subprocess.Popen(
        [shutil.which("node"), str(runtime / "bridge.cjs")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    timer = threading.Timer(600 if interactive else 90, process.kill)
    timer.daemon = True
    token_result = None
    timer.start()
    try:
        process.stdin.write(
            json.dumps(
                {
                    "cache_dir": str(cache),
                    "interactive": interactive,
                    "refresh": refresh,
                }
            )
        )
        process.stdin.close()
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                raise AuthError("Authentication helper returned an invalid response.") from None
            if not isinstance(event, dict):
                raise AuthError("Authentication helper returned an invalid message.")
            if event.get("event") == "device":
                uri, code = event.get("uri", ""), event.get("code", "")
                parsed = urlparse(uri)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname
                    not in {
                        "www.microsoft.com",
                        "microsoft.com",
                        "login.live.com",
                        "login.microsoftonline.com",
                    }
                    or not re.fullmatch(r"[A-Z0-9-]{4,20}", code)
                ):
                    raise AuthError("Unexpected Microsoft device-code response.")
                notify(f"Open {uri} and enter this code: {code}")
                if open_browser:
                    try:
                        webbrowser.open(uri)
                    except webbrowser.Error:
                        pass
            elif event.get("event") == "token":
                token, expires = event.get("token"), event.get("expires_at")
                if not isinstance(token, str) or not token or not isinstance(expires, (float, int)):
                    raise AuthError("Authentication helper returned invalid token metadata.")
                if not math.isfinite(expires) or expires <= time.time():
                    raise AuthError("Authentication helper returned an expired token.")
                token_result = token, float(expires)
            elif event.get("event") == "error":
                if event.get("code") == "LOGIN_REQUIRED":
                    raise AuthError(
                        "Microsoft sign-in is required again. Run login for this account."
                    )
                raise AuthError(
                    "Microsoft/Xbox/Minecraft authentication failed. Retry login; check your "
                    "account, Java license and service access. No credentials were printed."
                )
        process.wait()
        if process.returncode or token_result is None:
            raise AuthError("Authentication helper stopped or timed out; retry login.")
        return token_result
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def load_identity(directory: Path) -> dict:
    try:
        identity = json.loads((directory / "account.json").read_text())
        if not re.fullmatch(r"[0-9a-fA-F]{32}", identity["id"]):
            raise ValueError
        return identity
    except (OSError, ValueError, TypeError, KeyError):
        raise AuthError(
            "No valid saved account. Run login --account with this alias first."
        ) from None


class AccountToken:
    def __init__(self, account: str = "default", notify=lambda message: None):
        self.directory = account_directory(account)
        self.identity = load_identity(self.directory)
        self.notify = notify
        self.token = ""
        self.expires = 0.0

    def get(self, force: bool = False) -> str:
        if force or time.time() >= self.expires - 120:
            with FileLock(str(self.directory / "auth.lock"), timeout=0):
                token, expires = bridge_token(
                    self.directory, refresh=force, open_browser=False, notify=self.notify
                )
                with MinecraftClient() as client:
                    profile = client.profile(token)
                if profile["id"].lower() != self.identity["id"].lower():
                    raise AuthError(
                        "Refreshed session belongs to another profile; refusing to act."
                    )
                self.token, self.expires = token, expires
        return self.token

    def call(self, method, *args):
        try:
            return method(*args, self.get())
        except TokenRejected:
            # Read requests only: one credential refresh, then surface rejection.
            return method(*args, self.get(force=True))

    def profile(self, client: MinecraftClient) -> dict:
        profile = self.call(client.profile)
        if profile["id"].lower() != self.identity["id"].lower():
            raise AuthError(
                "Authenticated profile differs from the saved account; refusing to act."
            )
        return profile


def login(account: str, notify=lambda message: None, open_browser: bool = True) -> dict:
    directory = account_directory(account)
    with FileLock(str(directory / "auth.lock"), timeout=0):
        token, _ = bridge_token(
            directory, interactive=True, open_browser=open_browser, notify=notify
        )
        with MinecraftClient() as client:
            profile = client.profile(token)
            eligibility = client.eligibility(token)
        # Preserve identity: changing accounts requires a separate alias or logout.
        if (directory / "account.json").exists():
            old = load_identity(directory)
            if old["id"].lower() != profile["id"].lower():
                raise AuthError("This alias belongs to another profile. Use a new account alias.")
        atomic_write(directory / "account.json", json.dumps(profile) + "\n")
        return {**profile, "nameChangeAllowed": eligibility["nameChangeAllowed"]}


def logout(account: str) -> None:
    directory = account_directory(account)
    with FileLock(str(directory / "auth.lock"), timeout=0):
        identity_path = directory / "account.json"
        if identity_path.exists():
            identity = load_identity(directory)
            with profile_lock(identity["id"]):
                shutil.rmtree(directory / "tokens", ignore_errors=True)
                identity_path.unlink()
        else:
            shutil.rmtree(directory / "tokens", ignore_errors=True)


def profile_lock(profile_id: str) -> FileLock:
    if not re.fullmatch(r"[0-9a-fA-F]{32}", profile_id):
        raise ApiError("Invalid Minecraft profile ID.")
    directory = data_directory() / "locks"
    private_directory(directory)
    return FileLock(str(directory / f"{profile_id.lower()}.lock"), timeout=0)
