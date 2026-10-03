# Authentication and token configuration

Public `scan` requests need no account or token. Only `confirm` uses authentication.

## Which token?

The required credential is the **Minecraft Services access token** for your own licensed Java account. Microsoft sign-in normally passes through Microsoft OAuth, Xbox Live, XSTS, and finally Minecraft Services. The result of that last exchange is the token accepted by the availability endpoint.

A Microsoft password, OAuth access/refresh token, Xbox token, XSTS token, profile UUID, or launcher session identifier cannot replace it. This project does not implement that sign-in flow or provide token renewal. Use a trusted authentication client you control that explicitly returns a Minecraft Services access token; never paste account credentials into an unknown “token generator”.

For authentication implementers, see the [prismarine-auth project](https://github.com/PrismarineJS/prismarine-auth) and its Minecraft authentication examples. This is a reference, not a bundled dependency or promise that any particular Microsoft application configuration will work.

## Local setup

Copy `.env.example` to `.env` in the directory from which you run the command:

```dotenv
MC_ACCESS_TOKEN=your_minecraft_services_access_token
```

Paste the token alone: no `Bearer ` prefix. `.env` is excluded from Git. On Unix-like systems, restrict access with `chmod 600 .env`. On Windows, keep it in your private user directory and restrict access through filesystem permissions if the machine is shared.

```bash
mc-name-finder confirm --top 5
mc-name-finder confirm --env-file /path/to/private.env --top 5
```

An existing `MC_ACCESS_TOKEN` environment variable takes precedence over `.env`. If updating the file seems ineffective, clear a stale environment variable first. The file is loaded only for confirmation. No password, token or Authorization header is written to the result files or normal CLI output.

## Expiration and errors

Tokens expire and can be revoked. There is no fixed lifetime promised by this tool. On HTTP 401/403, confirmation stops and exports completed observations. Replace your token and rerun; previously completed checks are skipped unless you use `--refresh`.

A token represents account access. Do not include it in issue reports, screenshots, shell history, commits or shared output. `.gitignore` prevents ordinary accidental staging, but cannot undo a previously committed secret. If a real token is exposed, revoke the affected session through your account's security controls and obtain a fresh credential.

## Confirmation is read-only

`confirm` performs availability GET requests. It does not call the username-change endpoint, check your 30-day name-change eligibility, reserve a name or purchase a license. An `AVAILABLE` observation can become stale immediately.
