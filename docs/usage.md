# CLI reference

`mc-name-finder --help` and each subcommand's `--help` are available locally.

## scan

| Option | Default | Behavior |
|---|---|---|
| `--languages en fr` | `en fr` | Supported built-in corpora; one or both |
| `--min-length` / `--min` | `2` | Minimum normalized length |
| `--max-length` / `--max` | `6` | Maximum normalized length; up to 16 |
| `--min-frequency` | `0` | Minimum Zipf frequency, between 0 and 8; 3 is a practical starting point |
| `--limit N` | None | Highest-ranked N candidates overall, not N per length |
| `--words PATH` | None | UTF-8 input replaces built-in corpora; frequency threshold does not apply |
| `--output PATH` | `results` | Report directory, relative to your working directory |
| `--delay SECONDS` | `1` | Minimum public request spacing; cannot be below 1 |
| `--dry-run` | Off | Generate and export candidates without contacting Minecraft |
| `--resume` | Off | Load saved selection and check only `UNKNOWN` rows |
| `--overwrite` | Off | Start a fresh scan in an existing report directory |

Lengths must satisfy `2 <= min <= max <= 16`. Built-in candidates are ranked by frequency, then length, then alphabetically. Custom candidates have equal scores and are ordered by length/alphabetically. The limit includes two-letter words if your range includes them.

Resume uses the saved candidates and selection metadata; newly supplied language, length, frequency, limit and word-file settings do not alter the saved selection. Check timestamps are retained. Change the selection with a fresh scan and a different output, or `--overwrite`. Resuming an offline preview performs the previously skipped public checks. Resume and overwrite are mutually exclusive.

Output folders are not designed for concurrent writers. Do not set `--output` to a folder containing unrelated files named like the generated reports.

## confirm

| Option | Default | Behavior |
|---|---|---|
| `--output PATH` | `results` | Existing report directory |
| `--top N` | `20` | Number of highest-ranked unregistered, unconfirmed candidates |
| `--names NAME …` | None | Explicit names from the report; overrides top selection |
| `--env-file PATH` | `.env` | Explicit dotenv file path |
| `--delay SECONDS` | `16` | Minimum request spacing; cannot be below 16 |
| `--refresh` | Off | Include previously confirmed names |

Explicit names may be checked even if the public scan has not run or reported `TAKEN`. This is useful for a fresh authoritative check. Names must exist in the report and be at least three letters. Case is normalized. Missing names cause an error before any API calls.

The authenticated result is a separate observation from the public one; it does not rewrite the earlier public lookup. A name can therefore have `TAKEN` from an old scan and a newer `AVAILABLE` confirmation. Read both timestamps.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Command completed; empty candidate lists are valid |
| `1` | Configuration, file, network, authentication or API failure |
| `2` | Invalid CLI syntax / argument value |
| `130` | Ctrl+C interrupted API work; completed checks exported |

## API endpoints

- Public: `POST https://api.minecraftservices.com/minecraft/profile/lookup/bulk/byname`, body: array of up to 10 names.
- Authenticated: `GET https://api.minecraftservices.com/minecraft/profile/name/{name}/available`, Minecraft Services bearer token.

These service endpoints are not a versioned SDK contract. Community behavior can change; report unexpected responses with credentials removed. Primary implementation references include [NameSpyglass](https://github.com/LangTian0110/NameSpyglass) and [prismarine-auth](https://github.com/PrismarineJS/prismarine-auth); neither is a Mojang service guarantee.
