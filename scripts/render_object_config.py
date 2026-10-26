#!/usr/bin/env python3
"""Render Garage (S3-compatible) config into DATA_DIR."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--rpc-secret", required=True)
    parser.add_argument("--admin-token", required=True)
    parser.add_argument("--s3-region", default="garage")
    args = parser.parse_args()

    rpc = args.rpc_secret.strip()
    if len(rpc) != 64 or any(c not in "0123456789abcdefABCDEF" for c in rpc):
        raise SystemExit(
            "GARAGE_RPC_SECRET must be 32 bytes as hex (64 characters); "
            "run: openssl rand -hex 32"
        )

    root = args.data_root / "garage"
    meta = root / "meta"
    data = root / "data"
    meta.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)

    conf = f"""metadata_dir = "/var/lib/garage/meta"
data_dir = "/var/lib/garage/data"
db_engine = "sqlite"
replication_factor = 1
rpc_bind_addr = "[::]:3901"
rpc_public_addr = "garage:3901"
rpc_secret = "{rpc}"
bootstrap_peers = []

[s3_api]
s3_region = "{args.s3_region}"
api_bind_addr = "[::]:3900"
root_domain = ".s3.garage.localhost"

[s3_web]
bind_addr = "[::]:3902"
root_domain = ".web.garage.localhost"

[admin]
api_bind_addr = "[::]:3903"
admin_token = "{args.admin_token}"
metrics_token = "{args.admin_token}"
"""
    out = root / "garage.toml"
    if out.exists() and out.is_dir():
        raise SystemExit(
            f"{out} is a directory; remove it and re-run bootstrap-object.sh"
        )
    out.write_text(conf)
    out.chmod(0o600)


if __name__ == "__main__":
    main()
