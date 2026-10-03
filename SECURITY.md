# Security

For credential exposure, revoke the affected session immediately. Do not post the secret in a public issue.

For a code vulnerability, use the repository's private vulnerability reporting feature if it is enabled. Otherwise contact the maintainer through a private channel you already have; public issues are suitable only for non-sensitive reports.

The project uses a local Minecraft Services token for read-only availability checks. Tokens are sent only to the intended HTTPS endpoint; redirects are disabled. `.env` and generated result folders are ignored by Git. Always review staged files before committing.
