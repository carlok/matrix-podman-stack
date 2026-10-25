#!/usr/bin/env python3
"""Patch mautrix-telegram config.yaml for this stack."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--homeserver", required=True)
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--db-host", required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--db-password", required=True)
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--api-id", required=True)
    parser.add_argument("--api-hash", required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    cfg.setdefault("homeserver", {})["address"] = args.homeserver
    cfg["homeserver"]["domain"] = args.server_name

    cfg.setdefault("appservice", {})["address"] = "http://mautrix-telegram:29384"
    cfg["appservice"]["hostname"] = "0.0.0.0"
    cfg["appservice"]["port"] = 29384

    cfg.setdefault("telegram", {})["api_id"] = int(args.api_id)
    cfg["telegram"]["api_hash"] = args.api_hash

    cfg["database"] = (
        f"postgres://{args.db_user}:{args.db_password}"
        f"@{args.db_host}:5432/{args.db_name}?sslmode=disable"
    )

    args.config.write_text(yaml.safe_dump(cfg, sort_keys=False))


if __name__ == "__main__":
    main()
