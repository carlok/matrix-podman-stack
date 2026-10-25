#!/usr/bin/env python3
"""Render NATS and Valkey configs into DATA_DIR (no secrets in git)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def render_nats_conf(user: str, password: str) -> str:
    return f"""# Generated — do not commit
port: 4222
http: 127.0.0.1:8222
server_name: matrix-bus-nats

jetstream {{
  store_dir: "/data/jetstream"
  max_memory_store: 256MB
  max_file_store: 10GB
}}

authorization {{
  users = [
    {{ user: "{user}", password: "{password}" }}
  ]
}}
"""


def render_valkey_conf(password: str) -> str:
    return f"""# Generated — do not commit
bind 0.0.0.0
protected-mode yes
port 6379
requirepass {password}
appendonly yes
dir /data
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--nats-user", default=os.environ.get("NATS_USER", "bots"))
    parser.add_argument("--nats-password", required=True)
    parser.add_argument("--valkey-password", required=True)
    args = parser.parse_args()

    nats_dir = args.data_root / "nats"
    valkey_dir = args.data_root / "valkey"
    nats_dir.mkdir(parents=True, exist_ok=True)
    valkey_dir.mkdir(parents=True, exist_ok=True)
    (nats_dir / "jetstream").mkdir(parents=True, exist_ok=True)

    (nats_dir / "nats.conf").write_text(render_nats_conf(args.nats_user, args.nats_password))
    (valkey_dir / "valkey.conf").write_text(render_valkey_conf(args.valkey_password))
    for path in (nats_dir / "nats.conf", valkey_dir / "valkey.conf"):
        path.chmod(0o600)


if __name__ == "__main__":
    main()
