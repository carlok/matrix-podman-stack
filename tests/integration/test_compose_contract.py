"""Compose contract tests (no long-running stack)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _load_compose() -> dict:
    import subprocess

    proc = subprocess.run(
        ["podman-compose", "-f", str(ROOT / "compose.yaml"), "config"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return yaml.safe_load(proc.stdout)


@pytest.mark.timeout(60)
def test_long_running_services_use_unless_stopped_restart(integration_data_dir: Path):
    cfg = _load_compose()
    services = cfg.get("services", {})
    expect = {
        "synapse",
        "postgres-synapse",
        "element",
        "nats",
        "valkey",
        "garage",
        "prometheus",
        "grafana",
        "qdrant",
        "ollama",
        "postgres-telegram",
        "mautrix-telegram",
    }
    for name in expect:
        if name not in services:
            continue
        assert services[name].get("restart") == "unless-stopped", name
