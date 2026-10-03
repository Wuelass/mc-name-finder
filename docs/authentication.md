# Account login and token configuration

Public `scan` requires no account. For confirmation or automatic name changes, use a saved Microsoft login. A manual `.env` token remains available for read-only `confirm`.

## Microsoft device-code login

Install Python 3.10+ and **Node.js 20+ with npm**, then:

```bash
mc-name-finder login
mc-name-finder account
```

The first run installs the pinned authentication helper in local application data. The terminal prints a Microsoft URL and one-time code and opens the URL when possible. Enter the code on the Microsoft page, select your own account with a licensed Minecraft Java profile, and finish signing in. Never type your Microsoft password into the terminal or send it to the project.

The app displays the verified Java profile name and name-change eligibility. The helper uses the documented [PrismarineJS Java-token example](https://github.com/PrismarineJS/prismarine-auth/blob/master/docs/API.md), with its **Minecraft Nintendo Switch** client title. That name may appear on Microsoft’s sign-in page; you do not need a Switch. This project does not own the client registration and cannot guarantee Microsoft will continue accepting the flow. Sign-in rejection is surfaced as an error, not bypassed.

On a server without a browser:

```bash
mc-name-finder login --no-browser
```

Open the printed Microsoft URL on another device and enter the displayed code. The server process must keep running until sign-in completes.

## Multiple accounts

```bash
mc-name-finder login --account main
mc-name-finder login --account secondary
mc-name-finder account --account main
mc-name-finder watch TARGET_NAME --account main --claim --expected-profile CURRENT_NAME
```

Aliases are local labels, not Microsoft addresses. Each alias keeps its own cache and pinned UUID. An alias cannot silently switch to another UUID. Use a new alias or `logout` first when changing the connected account.

## Cache and refresh

Default storage locations:

| Platform | Location |
|---|---|
| Windows | `%LOCALAPPDATA%\MCNameFinder\` |
| Linux/macOS | `$XDG_CONFIG_HOME/mc-name-finder/`, or `~/.config/mc-name-finder/` |

`MC_NAME_FINDER_HOME` can explicitly override the root. The account metadata and latest `watch.json` contain no token. The `tokens/` subdirectory contains sensitive refresh/access credentials. Directories are private (0700) on Unix; cache files are 0600. New Windows directories restrict access to the current user with `icacls`. Data is protected by filesystem permissions, **not encrypted at rest**. Do not share or commit the cache.

Cached Minecraft tokens are refreshed before expiry. Read requests rejected with 401 can trigger one forced Minecraft-token refresh. Each freshly acquired token is checked against the saved profile UUID. If Microsoft requires interactive sign-in again, unattended work stops; run `login` and restart the watcher. Refresh never opens an unprompted login in the middle of unattended monitoring.

`logout --account ALIAS` removes this alias’s local token cache and identity. It does not revoke sessions remotely and retains watcher state to help reconcile an uncertain change. Microsoft account security controls remain the place to revoke exposed sessions.

## Manual token option

For an already obtained **Minecraft Services access token**:

```dotenv
MC_ACCESS_TOKEN=your_minecraft_services_access_token
```

Copy `.env.example` to `.env` and store the token locally without `Bearer `. Run `confirm --top 5`; use `--env-file PATH` for another location. An existing environment variable takes precedence over the file. Passwords, Microsoft OAuth tokens, Xbox/XSTS tokens and profile UUIDs are not Minecraft Services access tokens.

`confirm --account ALIAS --top 5` uses the saved Microsoft session instead and ignores `.env`. Manual tokens do not provide renewal and are not used by `watch`.

## Troubleshooting

- **Node/npm missing:** install Node.js LTS with npm and reopen your terminal.
- **Helper installation failed:** check internet/npm access; run `auth-setup` again.
- **Wrong Microsoft account selected:** use the correct browser account or a private browser window. New account identities need distinct aliases.
- **No Java profile or rejected sign-in:** verify the account can play Java and has an initialized profile. Microsoft/Xbox restrictions or service/client-registration rejection can also prevent login.
- **Name change allowed: False:** the account cannot change its name at present. The watcher refuses to arm a claim; check again when eligible.
- **Already in use:** another watcher, saved-account confirmation or auth operation holds a local lock. Stop it first. Locks are released when processes exit.
- **Uncertain change:** check the profile on Minecraft.net, then run `account` to reconcile the saved result before restarting.

Live sign-in and renaming require your account and network access. Automated tests verify protocols and mutation behavior with fake services; they never sign into Microsoft or rename a real account.
