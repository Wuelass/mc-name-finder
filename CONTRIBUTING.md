# Contributing

Small, focused pull requests are welcome. For a bug, include Python/OS versions, the command, expected behavior and redacted output. Never include `.env`, tokens, Authorization headers or account details.

## Local checks

```bash
python -m venv .venv
# Activate the venv, or use its explicit Python executable.
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest -q
node --test tests/node/auth-bridge.test.cjs
python -m build
```

Node.js 20+ is required for bridge tests. Tests must remain offline and deterministic. Mock HTTP and time instead of polling Minecraft. Add regression coverage when changing status interpretation, token handling, account pinning, claim reconciliation, retry behavior or persistence. Keep README examples and CLI help aligned with implementation.

## Design expectations

Preserve the distinction between public absence and authenticated availability, retain per-check timestamps, and fail closed on unexpected service responses. Keep tokens out of output and source control. Respect service backoff and retain upstream corpus attribution. If adding a dictionary, document its coverage and license before distributing it.
