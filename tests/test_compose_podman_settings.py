"""Compose settings that podman-compose 1.5 would otherwise change."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_podman_compose_does_not_place_services_in_a_pod():
    data = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert data["x-podman"]["in_pod"] is False


def test_valkey_keeps_kill_so_tini_can_forward_signals():
    data = yaml.safe_load((ROOT / "compose.yaml").read_text())
    valkey = data["services"]["valkey"]
    assert valkey["cap_drop"] == ["ALL"]
    assert "KILL" in valkey["cap_add"]
