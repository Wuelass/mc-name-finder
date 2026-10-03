# Architecture

The package lives under `src/mc_name_finder/` and exposes a console entry point plus `python -m mc_name_finder`.

| Module | Responsibility |
|---|---|
| `words.py` | Candidate model, normalization, source loading, deduplication and ranking |
| `api.py` | Minecraft Services requests, pacing, retries and response validation |
| `storage.py` | Atomic JSON checkpoints, CSV/text exports and attribution |
| `cli.py` | Arguments, selection, scan/confirm orchestration and terminal summaries |

## Data and observations

A candidate retains its normalized name, original spellings, source language, internal rank, public occupancy and exact availability. Public and authenticated checks have separate timestamps. A JSON report stores the full candidate selection and metadata; resume does not silently regenerate a potentially different source selection.

Public `UNKNOWN` rows become `TAKEN` or `UNREGISTERED` only after successful schema validation. Two-letter candidates receive `IMPOSSIBLE_LENGTH` at generation time. Exact `NOT_CHECKED` rows become `AVAILABLE`, `DUPLICATE` or `NOT_ALLOWED` after a valid authenticated response. Errors preserve the preceding observation.

JSON replacement is atomic within the filesystem: write a temporary sibling, then replace the destination. CSV and individual lists use the same technique, but the group of all output files is not a single transaction. JSON is the authoritative checkpoint if a crash interrupts export.

## Request handling

The client uses one session and paces request starts with a monotonic clock. Each logical request has at most four attempts; pacing also applies to retries. Numeric and HTTP-date `Retry-After` headers take priority over exponential fallback delays. A long server-requested wait is respected and can be interrupted with Ctrl+C.

401/403 stop the operation. Non-200 responses, malformed payloads and unrecognized statuses fail closed. Redirects are disabled. Raw response bodies and credential-bearing request objects are never included in user-facing API errors.

Tests inject fake sessions and clocks to verify API behavior without live service access. CLI integration tests exercise partial saves, resumption, timestamp preservation and token isolation.
