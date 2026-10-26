# Security hardening audit

**Repository:** `carlok/matrix-podman-stack`  
**Audit date:** 2026-10-26  
**Methodology (Trail of Bits skills, pin `196a9073ab10d35bacf111f945e02c00b2c6883a` on `main`):**

| Skill | Application |
|-------|-------------|
| `insecure-defaults` | Swept compose, `.env.example`, bootstrap templates for fail-open defaults, placeholder credentials, and empty env overrides. |
| `sharp-edges` | Reviewed config/env ergonomics (bot pattern + empty `BOT_NAME_PREFIX`, optional profile secrets, host nginx vs container binds). |
| `supply-chain-risk-auditor` | Reviewed pinned Python deps in `requirements-dev.txt`, `bots/example_bot/requirements.txt`, `scripts/requirements.txt` (manual/advisory; no `uv run collect.py` in CI). |
| `agentic-actions-auditor` | **N/A** — `.github/workflows/ci.yml` has no AI agent actions. |

**Container checklist:** cap_drop + minimal cap_add, `no-new-privileges`, `pids_limit`, mem limits (existing), non-root where feasible, `127.0.0.1` publishes, internal DB network, secrets required in compose, Synapse registration off / federation off (bootstrap), URL preview blacklist, metrics off public listener, bot token file permissions (existing scripts).

## Findings summary

| Severity | Issue | Evidence | Fix status |
|----------|-------|----------|------------|
| High | Telegram Postgres default password in compose | `compose.yaml` (was `TELEGRAM_POSTGRES_PASSWORD:-change_me_telegram_db`) | **Fixed** — required via `:?` |
| High | Grafana default admin password in compose | `compose.yaml` (was `GRAFANA_ADMIN_PASSWORD:-change_me_grafana`) | **Fixed** — required via `:?` |
| Medium | No container capability / privilege hardening | `compose.yaml` (no `cap_drop` / `security_opt` before audit) | **Fixed** — shared anchors; Valkey needs `CHOWN`/`DAC_OVERRIDE` |
| Medium | Postgres on same bridge as all services | `compose.yaml` `networks.matrix` only | **Fixed** — `matrix-db` internal network |
| Medium | Synapse metrics on client HTTP listener (`8008`) | `bootstrap/synapse-bootstrap.sh` | **Fixed** — metrics on `:9000`; Prometheus updated |
| Medium | No URL preview SSRF blacklist in generated Synapse config | `bootstrap/synapse-bootstrap.sh` | **Fixed** — `url_preview_ip_range_blacklist` |
| Medium | CI Actions floating `@v4` tags, broad default token perms | `.github/workflows/ci.yml` | **Fixed** — SHA pins + `permissions: contents: read` |
| Medium | Empty `BOT_NAME_PREFIX=` in `.env` breaks pattern bots | `.env.example`, `scripts/load_bot_config.py` | **Fixed** — treat empty env as unset; doc `.env.example` |
| Low | Element `read_only` rootfs incompatible with entrypoint | Element logs (`/etc/nginx/conf.d` write) | **Not applied** — documented; kept `pids_limit` + `no-new-privileges` |
| Low | Ollama API unauthenticated on localhost | `compose.yaml` `ollama` | **Not changed** — by design for local LLM profile; bound to `127.0.0.1` only |
| Low | Optional services still publish ports on loopback (NATS, Valkey, Garage, Qdrant) | `compose.yaml` | **Accepted** — host bots/tools; not exposed on `0.0.0.0` |
| Low | Image tags pinned, not digest-pinned | `compose.yaml` image lines | **Not fixed** — semver tags + Dependabot; digest pin left to operator |
| Info | Host nginx must block admin/metrics and set Element security headers | `README.md` nginx example | **Documented** for owner |
| Info | Registration disabled only in bootstrap-generated config | `bootstrap/synapse-bootstrap.sh` | **Existing** — owners must not enable open registration |
| Info | Bot tokens / admin token files | `scripts/create-bots.sh` (`chmod 600`, `umask 077`) | **Existing** |

## Synapse migration (existing `data/synapse/homeserver.yaml`)

New installs get the patched bootstrap automatically. **Upgrades** should:

1. Remove `metrics` from the `:8008` `listeners` resource names.
2. Add an HTTP listener on port `9000` with only the `metrics` resource (see fresh output from `synapse-bootstrap.sh`).
3. Add `url_preview_ip_range_blacklist` (same list as in bootstrap).
4. Restart Synapse; with monitoring profile, confirm `up{job="synapse"}` in Prometheus.

## Supply chain (Python)

Direct dependencies are version-pinned in `requirements-dev.txt` and bot `requirements.txt`. CI runs pytest/ruff only; operators should monitor PyPI advisories for `matrix-nio`, `aiohttp`, `PyYAML`, `redis`, `nats-py`. No install-time scripts in those manifests.

## Live verification (this audit branch)

| Check | Result |
|-------|--------|
| `podman compose up` (core + profiles exercised) | Pass |
| `scripts/test-bot-mention.sh` | Pass |
| `scripts/test-bot-duo.sh` | Pass |
| `scripts/verify-data-persistence.sh` | Pass |
| `scripts/verify-bus-persistence.sh` | Pass (after Valkey `cap_add` adjustment) |
| `scripts/verify-optional-profiles.sh` | Pass |
| Prometheus scrape `synapse:9000` | Pass (`up=1`) |
| `python3 -m pytest --cov` | Pass (93.53% total) |

## Owner actions (host nginx)

- Deny or return 404 for `/_synapse/admin` and `/_synapse/metrics` on public Synapse vhosts (example in `README.md`).
- Set Element CSP / security headers to match your homeserver URL in `connect-src`.
- Rotate any placeholder secrets from `.env.example` before production.
- Keep federation disabled unless you explicitly configure and understand the risk.
