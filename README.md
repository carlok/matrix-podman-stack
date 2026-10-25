# matrix-podman-stack

Private Matrix homeserver for Podman: **Synapse** + **Postgres**, **Element Web**, optional **mautrix-telegram**, optional **Prometheus/Grafana**, and helper scripts for **AI bot accounts**.

Designed for a small private group with humans and automation accounts (bots). Bot count and names are **config-driven** (`bots.yaml`). No federation, no bridges besides Telegram, no TURN/calls. **nginx stays on the host** — this stack only listens on `127.0.0.1`.

**Contact:** GitHub [@carlok](https://github.com/carlok)

## What you need

- Linux with **rootless Podman** and **podman compose** (or `podman-compose`)
- DNS for `SYNAPSE_SERVER_NAME` (and Element hostname) pointing at your server
- Host **nginx** (or similar) to TLS-terminate and reverse-proxy to local ports

Pinned images (see `compose.yaml`): Synapse `v1.163.2`, Element `v1.12.32`, Postgres `16.8-bookworm`, mautrix-telegram `v0.2610.0`, Prometheus `v3.2.1`, Grafana `11.5.2`.

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

## Monitoring (optional)

Enable the `monitoring` profile:

```bash
# set GRAFANA_ADMIN_PASSWORD in .env
COMPOSE_PROFILES=monitoring podman compose up -d
```

- Prometheus: `http://127.0.0.1:9090` (scrapes `/_synapse/metrics`)
- Grafana: `http://127.0.0.1:3000`

## Backup and upgrades

**Backup** (while stack is running or stopped):

- `data/postgres-synapse/` — Synapse database files
- `data/synapse/` — `homeserver.yaml`, signing keys, uploads
- `data/postgres-telegram/`, `data/mautrix-telegram/` — if using Telegram
- `data/bots/tokens.env` — bot credentials (keep off-site, encrypted)

Prefer `pg_dump` for Postgres-aware backups in production.

**Upgrade**:

1. Review release notes for Synapse / Element / bridge images.
2. Update pinned tags in `compose.yaml`.
3. `podman compose pull && podman compose up -d`
4. Watch `podman compose logs -f synapse` during DB migrations.

## systemd Quadlets (optional)

You can convert services to [Quadlets](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html): one `.container` file per service, `Wants=network-online.target`, volumes with `:Z` for rootless SELinux, and `PublishPort=127.0.0.1:8008:8008` on Synapse/Element. Keep the same env files and volume paths as `compose.yaml`.

## Layout

| Path | Purpose |
|------|---------|
| `compose.yaml` | Core stack + profiles `bootstrap`, `telegram`, `monitoring` |
| `scripts/bootstrap.sh` | One-shot Synapse + Element config generation |
| `bots.example.yaml` | Sample bot list / pattern (copy to `bots.yaml`) |
| `scripts/create-bots.sh` | Provision bot users from `bots.yaml` |
| `bots/example_bot/` | Minimal `matrix-nio` bot |
| `data/` | Runtime data (gitignored) |

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
