#!/usr/bin/env python3
"""Render Qdrant config with API key into DATA_DIR."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()

    root = args.data_root / "qdrant"
    storage = root / "storage"
    storage.mkdir(parents=True, exist_ok=True)

    conf_path = root / "config.yaml"
    if conf_path.exists() and conf_path.is_dir():
        raise SystemExit(
            f"{conf_path} is a directory; remove it and re-run bootstrap-vectors.sh"
        )

    conf = f"""log_level: INFO
storage:
  storage_path: /qdrant/storage
service:
  api_key: {args.api_key}
  enable_tls: false
"""
    conf_path.write_text(conf)
    conf_path.chmod(0o600)


if __name__ == "__main__":
    main()
