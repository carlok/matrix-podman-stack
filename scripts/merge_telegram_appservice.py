#!/usr/bin/env python3
"""Ensure Synapse loads the Telegram appservice registration file."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--homeserver", type=Path, required=True)
    args = parser.parse_args()

    if not args.homeserver.exists():
        raise SystemExit(f"Missing {args.homeserver} — run scripts/bootstrap.sh first")

    cfg = yaml.safe_load(args.homeserver.read_text())
    reg = "/data/telegram-registration.yaml"
    files = list(cfg.get("app_service_config_files") or [])
    if reg not in files:
        files.append(reg)
    cfg["app_service_config_files"] = files
    args.homeserver.write_text(yaml.safe_dump(cfg, sort_keys=False))


if __name__ == "__main__":
    main()
