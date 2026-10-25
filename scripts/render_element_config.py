#!/usr/bin/env python3
"""Render Element Web config.json from public URLs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--homeserver-url", required=True)
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    homeserver_url = args.homeserver_url.rstrip("/")
    config = {
        "default_server_config": {
            "m.homeserver": {
                "base_url": homeserver_url,
                "server_name": args.server_name,
            },
            "m.identity_server": {
                "base_url": "https://vector.im",
            },
        },
        "brand": "Element",
        "disable_guests": True,
        "features": {
            "feature_video_rooms": False,
            "feature_element_call_video_rooms": False,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
