# Security

For credential exposure, revoke the affected session immediately. Do not post the secret in a public issue.

For a code vulnerability, use the repository's private vulnerability reporting feature if it is enabled. Otherwise contact the maintainer through a private channel you already have; public issues are suitable only for non-sensitive reports.

The project uses Minecraft Services tokens for availability checks and explicit `watch --claim` name changes. Device-code login stores refresh credentials in a private local cache; Unix directories use 0700 and files use 0600, while new Windows cache directories restrict access to the current user through ACLs. Cache contents are not encrypted at rest, so treat them as account credentials. Tokens are sent only to the intended HTTPS endpoint; redirects are disabled. `.env`, generated result folders and local Node dependencies are ignored by Git. Account caches default to application data outside the repository. Always review staged files before committing.
