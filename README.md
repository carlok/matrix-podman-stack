# matrix-podman-stack

Private Matrix homeserver for Podman: **Synapse** + **Postgres**, **Element Web**, optional **mautrix-telegram**, optional **Prometheus/Grafana**, and helper scripts for **AI bot accounts**.

Designed for a small private group with humans and automation accounts (bots). Bot count and names are **config-driven** (`bots.yaml`). No federation, no bridges besides Telegram, no TURN/calls. **nginx stays on the host** — this stack only listens on `127.0.0.1`.

**Contact:** GitHub [@carlok](https://github.com/carlok)

## What you need

- Linux with **rootless Podman** and **podman compose** (or `podman-compose`)
- DNS for `SYNAPSE_SERVER_NAME` (and Element hostname) pointing at your server
- Host **nginx** (or similar) to TLS-terminate and reverse-proxy to local ports

Pinned images (see `compose.yaml`): Synapse `v1.163.2`, Element `v1.12.32`, Postgres `16.9-bookworm`, mautrix-telegram `v0.2610.0`, Prometheus `v3.5.0`, Grafana `11.5.2`.

## Sizing (CPU / RAM)

Measured on a Linux host with **Podman 4.9.3** (`podman stats --no-stream`), stack idle ≥45s after health checks, **2026-10-25**. Container memory is cgroup usage; host bot processes run outside Podman.

### Per service (idle)

| Service | Profile | Idle CPU | Idle RAM |
|---------|---------|----------|----------|
| `postgres-synapse` | core | ~0.15–0.24% | ~22–35 MiB |
| `synapse` | core | ~1.1–3.2% | ~115–121 MiB |
| `element` | core | ~0.06–0.4% | ~4 MiB |
| `nats` | `bus` | ~0.12–0.23% | ~2.5–3 MiB |
| `valkey` | `bus` | ~0.11–0.18% | ~2.8 MiB |
| `prometheus` | `monitoring` | ~0.05–0.31% | ~17–18 MiB |
| `grafana` | `monitoring` | ~0.8–3% | ~58–62 MiB |
| `postgres-telegram` | `telegram` | ~0.06–0.23% | ~4.4 MiB |
| `mautrix-telegram` | `telegram` | low when configured* | ~80–200 MiB typical† |
| `garage` | `object` | ~0.5% | ~4 MiB |
| `qdrant` | `vectors` | ~0.1–0.4% | ~21–23 MiB |
| `ollama` | `llm` | ~0.01–0.1% | ~9 MiB (daemon only, **no model**) |

| Host process | When | Idle CPU | Idle RAM |
|--------------|------|----------|----------|
| `bots/example_bot/bot.py` | 2 bots syncing | ~1.2% each | ~44 MiB RSS each |

\*Before `bootstrap-telegram.sh` and bridge login, mautrix may restart in a tight loop (high CPU, misleadingly low RSS).

†After Telegram login; depends on bridge traffic and Python heap.

**Ollama with a model:** pulling `tinyllama` or similar adds **hundreds of MiB to several GiB** RAM while inferring; size the host from [Ollama model cards](https://ollama.com/library), not the idle daemon row above.

Reproduce a snapshot: `./scripts/collect-resource-stats.sh 'my scenario'`.

### Recommended host (containers + modest headroom)

| Scenario | vCPU | RAM | Notes |
|----------|------|-----|--------|
| **Core only** (Synapse + Postgres + Element) | 2 | **4 GiB** | ~160 MiB containers idle; room for OS, nginx, 2–4 host bots |
| **Core + `bus`** | 2 | **4 GiB** | +~6 MiB for NATS + Valkey |
| **All profiles except `llm`** | 4 | **8 GiB** | Core + bus + monitoring + telegram + object + vectors (~500 MiB containers idle) + bots |
| **With `llm` (Ollama)** | 4+ | **16 GiB+** | Add model RAM/VRAM on top; raise `OLLAMA_MEM_LIMIT` in `.env` if you cap the container |

Optional **memory limits** (`mem_limit` in `compose.yaml`, defaults in comments) can be overridden via `.env` — see `POSTGRES_MEM_LIMIT`, `SYNAPSE_MEM_LIMIT`, `OLLAMA_MEM_LIMIT`, etc. in `.env.example`. Caps protect the host on small VPS instances; set Ollama’s limit above your largest model or remove the cap for heavy local inference.

## Quick start

### 1. DNS

Create records for your Matrix domain, for example:

- `matrix.example.com` → your server (Synapse / client API)
- `chat.example.com` → your server (Element Web)

`SYNAPSE_SERVER_NAME` must match the Matrix server name (usually the Synapse hostname).

### 2. Clone and configure

```bash
git clone https://github.com/carlok/matrix-podman-stack.git
cd matrix-podman-stack
cp .env.example .env
```

Edit `.env`:

- Set `SYNAPSE_SERVER_NAME`, `PUBLIC_HOMESERVER_URL`, `PUBLIC_ELEMENT_URL`
- Replace all `change_me_*` secrets (`openssl rand -hex 32`)

Install script dependencies on the host (for bootstrap helpers):

```bash
python3 -m pip install --user -r scripts/requirements.txt
```

### 3. Bootstrap Synapse data

Generates `data/synapse/homeserver.yaml` (Postgres, registration off, federation off) and Element `config.json`:

```bash
chmod +x scripts/*.sh bootstrap/*.sh
./scripts/bootstrap.sh
```

### 4. Start core stack

```bash
podman compose up -d
podman compose ps
```

Wait until `synapse` is **healthy** (`curl -fsS http://127.0.0.1:8008/health`).

### 5. Create admin and human users

Registration is disabled. Create an admin:

```bash
source .env
podman compose exec synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  -u admin -p 'YOUR_STRONG_PASSWORD' -a \
  http://localhost:8008
```

Create additional users with `--no-admin` instead of `-a`.

Use Element at `http://127.0.0.1:8080` locally, or via your public URL after nginx is configured.

### 6. Configure and create bot accounts

Copy the sample bot config and edit names/count:

```bash
cp bots.example.yaml bots.yaml
```

Two modes (see comments in `bots.example.yaml`):

- **Explicit list** — `bots:` with `localpart` + optional `display_name` per account (good for named roles).
- **Pattern** — `pattern.prefix` + `pattern.count` generates `prefix1`, `prefix2`, … with optional `display_name_template` (`{index}` is 1-based).

Optional `.env` overrides: `BOT_CONFIG`, `BOT_COUNT`, `BOT_NAME_PREFIX` (pattern mode only).

Provision Matrix users and token file:

```bash
./scripts/create-bots.sh
```

Tokens are written to `data/bots/tokens.env` (`chmod 600`). The script **does not print tokens**. Each bot gets variables like `BOT_<LOCALPART>_USER_ID` / `BOT_<LOCALPART>_ACCESS_TOKEN` (see the file after creation). `BOT_IGNORE_MATRIX_IDS` is populated for loop prevention.

When `SYNAPSE_ADMIN_PASSWORD` (or `TEST_ADMIN_PASSWORD`) is set, `create-bots.sh` also:

- Applies Synapse admin [`override_ratelimit`](https://element-hq.github.io/synapse/latest/admin_api/user_admin.html#override-ratelimit) for each bot (and admin) — defaults `BOT_RATELIMIT_MPS` / `BOT_RATELIMIT_BURST` (integers).
- Rotates passwords for existing bot accounts via the admin API so tokens can be refreshed safely.

Bootstrap sets relaxed `rc_login` / `rc_message` defaults for small private servers; tighten them in `data/synapse/homeserver.yaml` for production.

### 7. Invite bots to a private room

In Element, create a private room and invite the bot MXIDs from `data/bots/tokens.env` (e.g. `@bot1:your.domain` when using the default pattern).

### 8. Run the example bot

Pick one bot from `data/bots/tokens.env` (example uses the first entry from `bots.yaml`):

```bash
python3 -m venv .venv-bot
source .venv-bot/bin/activate
pip install -r bots/example_bot/requirements.txt
set -a && source data/bots/tokens.env && set +a
export MATRIX_HOMESERVER_URL=http://127.0.0.1:8008
# Example for localpart "bot1" → env prefix BOT_BOT1_
export MATRIX_USER_ID="$BOT_BOT1_USER_ID"
export MATRIX_ACCESS_TOKEN="$BOT_BOT1_ACCESS_TOKEN"
export BOT_DISPLAY_NAME="$BOT_BOT1_DISPLAY_NAME"
export SYNAPSE_SERVER_NAME="$SYNAPSE_SERVER_NAME"
python bots/example_bot/bot.py
```

Mention the bot’s `@localpart` in a joined room; you should get a stub reply. Set `LLM_PROVIDER_KEY` to wire a real provider in `bots/example_bot/bot.py`.

By default the example bot ignores senders listed in `BOT_IGNORE_MATRIX_IDS` and localparts matching `BOT_IGNORE_LOCALPART_REGEX` (default `^bot\d+$`). Set `BOT_IGNORE_OTHER_BOTS=false` to disable pattern-based ignores.

## nginx example (on the host)

TLS certificates are your choice (e.g. certbot). Example server blocks:

```nginx
# Synapse client API
server {
    listen 443 ssl http2;
    server_name matrix.example.com;

    # ssl_certificate ...;
    # ssl_certificate_key ...;

    # Do not expose Synapse admin API or Prometheus metrics via the public vhost.
    location ~ ^/_synapse/(admin|metrics) {
        return 404;
    }

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $host;
        client_max_body_size 50M;
    }
}

# Element Web
server {
    listen 443 ssl http2;
    server_name chat.example.com;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    # Tighten Content-Security-Policy for your deployment (Element needs script/style from its origin).
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https://matrix.example.com; frame-ancestors 'self';" always;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Update `.env` `PUBLIC_*` URLs to match your HTTPS URLs and re-run `./scripts/bootstrap.sh` (or only re-render Element config) if you change them.

## Telegram bridge (optional)

1. Create an app at [my.telegram.org](https://my.telegram.org) and note **api_id** and **api_hash**.
2. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_POSTGRES_PASSWORD` in `.env`.
3. Run:

```bash
./scripts/bootstrap-telegram.sh
COMPOSE_PROFILES=telegram podman compose up -d
podman compose restart synapse
```

4. Follow [mautrix-telegram](https://docs.mau.fi/bridges/python/telegram/index.html) docs to log in (e.g. `COMPOSE_PROFILES=telegram podman compose exec mautrix-telegram ...`).

## Bot bus (optional profile `bus`)

Lightweight **task queue** and **shared KV** for master/worker bots (off by default):

| Service | Image | Use for |
|---------|-------|---------|
| [NATS](https://nats.io/) + JetStream | `nats:2.11.4-alpine` | Durable queues/streams — master publishes tasks, workers consume (`bot.tasks.*`) |
| [Valkey](https://valkey.io/) | `valkey:8.1.2-alpine` | Redis-compatible KV — shared state, locks, short-lived flags |

Both require auth (`NATS_USER` / `NATS_PASSWORD`, `VALKEY_PASSWORD` in `.env`). They listen on the internal `matrix` network; optional localhost ports are `127.0.0.1` only (`NATS_CLIENT_PORT`, `NATS_MONITOR_PORT`, `VALKEY_PORT`).

```bash
# set NATS_PASSWORD and VALKEY_PASSWORD in .env
./scripts/bootstrap-bus.sh
COMPOSE_PROFILES=bus podman compose up -d
./scripts/verify-bus-persistence.sh   # auth + down -v survival smoke test
```

Persistence (under `DATA_DIR`): `nats/jetstream/` (JetStream file store), `nats/nats.conf` (generated, chmod 600), `valkey/` (AOF/RDB + generated `valkey.conf`).

Example bot (optional): set `BUS_DEMO=true`, `NATS_URL=nats://bots:PASSWORD@nats:4222`, and `VALKEY_PASSWORD` when the profile is up — on each @mention it publishes a JetStream event and writes a shared Valkey key (see `bots/example_bot/bus_hooks.py`).

## Monitoring (optional)

Enable the `monitoring` profile:

```bash
# set GRAFANA_ADMIN_PASSWORD in .env
mkdir -p data/prometheus data/grafana
COMPOSE_PROFILES=monitoring HOST_UID=$(id -u) HOST_GID=$(id -g) podman compose up -d
```

- Prometheus: `http://127.0.0.1:9090` (scrapes `/_synapse/metrics`)
- Grafana: `http://127.0.0.1:3000`

## Persistent data (`DATA_DIR`)

All state lives on the host under **`DATA_DIR`** (default `./data`, set in `.env`). `compose.yaml` uses **bind mounts only** — no named or anonymous volumes — so data survives `podman compose down`, `podman compose down -v`, image upgrades, and reboots.

| Host path (under `DATA_DIR`) | Contents |
|------------------------------|----------|
| `postgres-synapse/` | Synapse Postgres data directory |
| `postgres-telegram/` | mautrix-telegram Postgres (profile `telegram`) |
| `synapse/` | `homeserver.yaml`, signing key, `homeserver.log`, `media_store/`, `uploads/` |
| `element/config.json` | Element Web client config |
| `mautrix-telegram/` | Bridge config, registration, session DB files |
| `prometheus/`, `grafana/` | Monitoring profile TSDB / Grafana lib |
| `bots/tokens.env`, `bots/admin.token` | Bot and admin API tokens (`chmod 600`) |
| `nats/jetstream/`, `nats/nats.conf` | NATS JetStream store + generated config (profile `bus`) |
| `valkey/` | Valkey AOF/RDB + generated `valkey.conf` (profile `bus`) |

**Rootless ownership:** Synapse and Prometheus run as `HOST_UID`/`HOST_GID` (default `1000`). Element and Grafana run as `root` in the container namespace (nginx/Grafana bind low ports). After copying a tarball from another machine, fix ownership:

```bash
export HOST_UID=$(id -u) HOST_GID=$(id -g)
podman unshare chown -R "$HOST_UID:$HOST_GID" "$DATA_DIR/synapse" "$DATA_DIR/prometheus" "$DATA_DIR/postgres-synapse"
```

On SELinux hosts, compose uses `:Z` on bind mounts for rootless Podman.

**Check persistence:** `./scripts/verify-data-persistence.sh` (creates a room/message, uploads media, runs `podman compose down -v`, brings the stack back, asserts data is still present).

## Backup and upgrades

**Backup** (stop the stack, then copy the tree):

```bash
podman compose down
tar -czf matrix-backup-$(date -u +%F).tar.gz -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"
```

Optional Postgres-aware dumps while running:

```bash
podman compose exec postgres-synapse pg_dump -U synapse synapse > synapse.sql
```

Keep `bots/tokens.env` encrypted off-site.

**Upgrade**:

1. Review release notes for Synapse / Element / bridge images.
2. Update pinned tags in `compose.yaml`.
3. `podman compose pull && podman compose up -d`
4. Watch `podman compose logs -f synapse` during DB migrations.

## Start stack after host reboot (opt-in)

Every long-running service in `compose.yaml` uses **`restart: unless-stopped`** so Podman can bring containers back after a daemon restart. One-shot **`synapse-bootstrap`** uses **`restart: "no"`** (run only via `COMPOSE_PROFILES=bootstrap`).

### Option A — Podman restart service (simple)

Restarts **all** containers on the host that were running with a restart policy (not only this stack).

**Rootless:**

```bash
loginctl enable-linger "$USER"
systemctl --user enable --now podman-restart.service
```

**Rootful:**

```bash
sudo systemctl enable --now podman-restart.service
```

After reboot, run `podman ps` to confirm containers are up. A full host reboot was not exercised in CI; behavior depends on your Podman/systemd version.

### Option B — systemd user unit for this compose project

Generates `~/.config/systemd/user/matrix-podman-stack.service` (honours `COMPOSE_PROFILES` from `.env` or `--profiles`):

```bash
./scripts/install-systemd-service.sh
systemctl --user daemon-reload
systemctl --user enable --now matrix-podman-stack.service
loginctl enable-linger "$USER"   # rootless: start at boot without login session
```

Remove with `./scripts/install-systemd-service.sh --uninstall`.

Verify restart policy on a container: `podman inspect --format '{{.HostConfig.RestartPolicy.Name}}' <container>` → `unless-stopped`.

### Advanced: Quadlets

You can also convert services to [Quadlets](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html) (one unit per container). Same volume paths and `127.0.0.1` publishes as `compose.yaml`.

## Bot duo mode (optional)

Default behavior stays safe: **`BOT_IGNORE_OTHER_BOTS=true`** and normal **@mention** replies only.

Enable a bounded **master/worker** thread (deterministic stub text, LLM hook unchanged):

1. Run two bot processes (e.g. `bot1` master, `bot2` worker) with `BOT_DUO_ENABLED=true`, `BOT_IGNORE_OTHER_BOTS=false`, and reciprocal `BOT_DUO_PEER_MXIDS`.
2. In a room with both bots, a human sends **`!discuss <topic>`** (prefix configurable).
3. Guards: **`BOT_MAX_TURNS`**, stop marker **`BOT_DUO_STOP_MARKER`** (default `[DONE]`), **cooldown**, **event dedupe**, **human message resets** the thread, meta replies as **`m.notice`**, state under **`BOT_DUO_STATE_DIR`** (default `data/bots/duo-state`).

Smoke test: `./scripts/test-bot-duo.sh` (requires two bots in `bots.yaml` and `TEST_ADMIN_PASSWORD`).

## Layout

| Path | Purpose |
|------|---------|
| `compose.yaml` | Core stack + profiles `bootstrap`, `telegram`, `monitoring`, `bus`, `object`, `vectors`, `llm` |
| `scripts/collect-resource-stats.sh` | `podman stats` snapshot for sizing |
| `scripts/install-systemd-service.sh` | Optional systemd user unit for `podman compose up -d` at boot |
| `scripts/test-bot-duo.sh` | Duo mode E2E (turn cap + stop marker) |
| `scripts/bootstrap.sh` | One-shot Synapse + Element config generation |
| `bots.example.yaml` | Sample bot list / pattern (copy to `bots.yaml`) |
| `scripts/create-bots.sh` | Provision bot users from `bots.yaml` |
| `bots/example_bot/` | Minimal `matrix-nio` bot |
| `DATA_DIR/` (default `./data/`) | All bind-mounted runtime state (gitignored) |
| `scripts/verify-data-persistence.sh` | `down -v` survival smoke test |

## Testing (unit tests and coverage)

Python unit tests use **pytest** and **pytest-cov** (no live Matrix server required). Install dev dependencies and run:

```bash
python3 -m pip install -r requirements-dev.txt
pytest --cov --cov-report=term-missing --cov-branch
```

Coverage thresholds and measured modules are defined in `pyproject.toml`. Contributors and agents should read `AGENT.md` (run tests before every commit; do not let coverage drop).

Optional shell tests for `scripts/install-systemd-service.sh`:

```bash
bats tests/bats/
```

CI runs the unit-test job on every push/PR and uploads `coverage.xml` as an artifact. Current gate (measured modules in `pyproject.toml`): **59** tests, **95.51%** line / **88.57%** branch coverage overall (`fail_under` **93%** combined).

## Validate compose file

```bash
podman compose config
```

## Optional: temporary HTTPS via Cloudflare Quick Tunnel (test only)

For a one-off check without configuring nginx/TLS on the host, you can expose local ports with [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) (`cloudflared`). **Do not use this in production** — URLs are public and ephemeral.

```bash
# Synapse API (replace port if you changed SYNAPSE_HTTP_PORT)
cloudflared tunnel --url http://127.0.0.1:8008
# In another terminal — Element Web
cloudflared tunnel --url http://127.0.0.1:8080
```

1. Copy the `https://*.trycloudflare.com` URL for Synapse and verify: `curl -fsS "$SYNAPSE_URL/_matrix/client/versions"`.
2. Re-render Element so it points at the Synapse tunnel URL, then restart Element:
   `python3 scripts/render_element_config.py --homeserver-url "$SYNAPSE_URL" --server-name "$SYNAPSE_SERVER_NAME" --output data/element/config.json && podman compose restart element`
3. Open the Element tunnel URL in a browser (homeserver in `config.json` must match the Synapse tunnel URL).
4. Stop `cloudflared` when finished. **Never commit tunnel URLs or generated tokens.**

On rootless Podman, Element’s container runs as `root` inside the namespace so nginx can bind port 80 (see `compose.yaml`).

## Security / public repository

This repo is public. Only `.env.example`, `bots.example.yaml`, and templates are committed. Keep `.env`, `bots.yaml`, `data/`, and `data/bots/tokens.env` local and out of git.

Compose applies baseline container hardening (`cap_drop`, `no-new-privileges`, `pids_limit`, internal DB network, `127.0.0.1` port binds). See [docs/SECURITY-AUDIT.md](docs/SECURITY-AUDIT.md) for the full audit and migration notes (for example Synapse metrics on port `9000` inside the stack network).

Rootless Podman: services that write bind mounts use `userns_mode: keep-id` with `HOST_UID` / `HOST_GID` (see `compose.yaml`).

## License

Copyright 2026 Carlo Perassi.

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.
