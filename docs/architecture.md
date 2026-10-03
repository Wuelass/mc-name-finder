# Architecture

The package lives under `src/mc_name_finder/` and exposes a console entry point plus `python -m mc_name_finder`.

| Module | Responsibility |
|---|---|
| `words.py` | Candidate model, normalization, source loading, deduplication and ranking |
| `api.py` | Minecraft Services requests, pacing, retries and response validation |
| `storage.py` | Atomic JSON checkpoints, CSV/text exports and attribution |
| `cli.py` | Arguments, scan/confirm/account/watch orchestration and terminal summaries |
| `auth.py` | Private cache directories, helper setup, Microsoft session refresh and UUID binding |
| `watch.py` | One-target scheduler, explicit claim mode and durable outcome reconciliation |
| `node/bridge.cjs` | JSON-line protocol around the pinned PrismarineJS device-code flow |

## Data and observations

A candidate retains its normalized name, original spellings, source language, internal rank, public occupancy and exact availability. Public and authenticated checks have separate timestamps. A JSON report stores the full candidate selection and metadata; resume does not silently regenerate a potentially different source selection.

Public `UNKNOWN` rows become `TAKEN` or `UNREGISTERED` only after successful schema validation. Two-letter candidates receive `IMPOSSIBLE_LENGTH` at generation time. Exact `NOT_CHECKED` rows become `AVAILABLE`, `DUPLICATE` or `NOT_ALLOWED` after a valid authenticated response. Errors preserve the preceding observation.

JSON replacement is atomic within the filesystem: write a temporary sibling, then replace the destination. CSV and individual lists use the same technique, but the group of all output files is not a single transaction. JSON is the authoritative checkpoint if a crash interrupts export.

## Request handling

The client uses one session and paces request starts with a monotonic clock. Each logical request has at most four attempts; pacing also applies to retries. Numeric and HTTP-date `Retry-After` headers take priority over exponential fallback delays. A long server-requested wait is respected and can be interrupted with Ctrl+C.

401 can trigger one saved-session refresh on read operations. Persistent 401/403 stop the operation. Non-200 responses, malformed payloads and unrecognized statuses fail closed. Redirects are disabled. Raw response bodies and credential-bearing request objects are never included in user-facing API errors.

Tests inject fake sessions and clocks to verify API behavior without live service access. CLI integration tests exercise partial saves, resumption, timestamp preservation and token isolation.


## Name changes

`watch --claim` is the only mutating command. The engine pins a UUID/current name, checks eligibility and writes `CLAIMING` durably before one PUT. Network errors or unexpected write responses are uncertain outcomes. A profile GET confirms success; uncertain or unverified outcomes block rearming until `account` reconciles them. Writes never pass through the generic read retry loop.

A file lock keyed by UUID prevents overlapping watchers in the same application-data directory. The auth cache has a separate per-alias lock. The Node bridge retains refresh credentials; Python holds the Minecraft token in memory and validates a freshly acquired token’s UUID before use. Node stdout is captured as a private protocol pipe, raw library logging is suppressed, and stderr is discarded rather than exposing credential-bearing failures. Interactive device events contain only the Microsoft URL and one-time user code.
