# Security policy

## Supported versions

Security fixes are applied on the **`main`** branch. Use the latest commit on `main` or the most recent release tag when deploying.

| Version / branch | Supported |
|------------------|-----------|
| `main`           | Yes       |
| Older tags       | No        |

## Reporting a vulnerability

**Do not** open a public GitHub issue for security vulnerabilities.

Report issues privately using [GitHub Security Advisories](https://github.com/carlok/matrix-podman-stack/security/advisories/new) (private vulnerability reporting) for this repository. Include steps to reproduce, impact, and any suggested fix if you have one.

We will acknowledge reports and work on a fix on a reasonable timeline. Coordinated disclosure is appreciated.

## Secrets and sensitive data

This repository is public. **Never commit secrets**, including:

- `.env` (gitignored; use `.env.example` as a template only)
- Bot or admin tokens under `data/` (for example `data/bots/tokens.env`)
- TLS private keys, registration shared secrets, or bridge credentials

Runtime state lives under `data/` and is excluded from git. If you accidentally commit a secret, rotate it immediately and remove it from history if needed.

For general deployment hygiene, see the **Security / public repository** section in [README.md](README.md).
