"""Tests for NATS / Valkey config rendering."""

from __future__ import annotations

from scripts.render_bus_config import render_nats_conf


def test_nats_monitor_binds_all_interfaces():
    text = render_nats_conf("bots", "secret")
    assert "http: 0.0.0.0:8222" in text
