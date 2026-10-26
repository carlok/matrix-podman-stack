#!/usr/bin/env python3
"""Load bot provisioning config from YAML + optional .env overrides."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

VALID_LOCALPART = re.compile(r"^[a-z0-9._=\-/]+$", re.IGNORECASE)


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return int(raw)


def _display_name(entry: dict[str, Any], localpart: str, index: int | None) -> str:
    if entry.get("display_name"):
        return str(entry["display_name"])
    template = entry.get("display_name_template")
    if template and index is not None:
        return template.replace("{index}", str(index))
    return localpart


def load_config(path: Path) -> list[dict[str, str]]:
    data = yaml.safe_load(path.read_text()) or {}

    if data.get("bots"):
        bots: list[dict[str, str]] = []
        for item in data["bots"]:
            localpart = str(item["localpart"]).strip().lower()
            if not VALID_LOCALPART.match(localpart):
                raise ValueError(f"Invalid localpart: {localpart}")
            bots.append(
                {
                    "localpart": localpart,
                    "display_name": _display_name(item, localpart, None),
                }
            )
        return bots

    pattern = data.get("pattern") or {}
    env_prefix = os.environ.get("BOT_NAME_PREFIX", "").strip()
    if env_prefix:
        prefix = env_prefix
    elif "prefix" in pattern:
        prefix = str(pattern.get("prefix") or "").strip()
    else:
        prefix = "bot"
    count = _env_int("BOT_COUNT")
    if count is None:
        count = int(pattern.get("count", 1))
    template = pattern.get("display_name_template")

    if count < 1:
        raise ValueError("Bot count must be >= 1")
    if not prefix:
        raise ValueError("pattern.prefix / BOT_NAME_PREFIX must be non-empty")

    bots = []
    for i in range(1, count + 1):
        localpart = f"{prefix}{i}"
        if not VALID_LOCALPART.match(localpart):
            raise ValueError(f"Invalid generated localpart: {localpart}")
        entry = {"display_name_template": template} if template else {}
        bots.append(
            {
                "localpart": localpart,
                "display_name": _display_name(entry, localpart, i),
            }
        )
    return bots


def env_key(localpart: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]", "_", localpart).upper()
    return f"BOT_{safe}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML config path (default: BOT_CONFIG env or bots.yaml / bots.example.yaml)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON list of bots")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if args.config is not None:
        config = args.config
    else:
        env_path = os.environ.get("BOT_CONFIG", "").strip()
        config = Path(env_path) if env_path else root / "bots.yaml"
        if not config.is_file():
            fallback = root / "bots.example.yaml"
            if fallback.is_file():
                config = fallback
            else:
                raise SystemExit(f"No bot config found at {config}")
    if not config.is_file():
        raise SystemExit(f"Bot config not found: {config}")

    bots = load_config(config)
    if args.json:
        print(json.dumps(bots))
    else:
        for bot in bots:
            print(f"{bot['localpart']}\t{bot['display_name']}")


if __name__ == "__main__":
    main()
