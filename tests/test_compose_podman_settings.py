"""Compose settings that podman-compose 1.5 would otherwise change."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_podman_compose_does_not_place_services_in_a_pod():
    data = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert data["x-podman"]["in_pod"] is False
