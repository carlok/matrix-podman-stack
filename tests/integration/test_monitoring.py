"""Prometheus scrapes Synapse; Grafana queries Prometheus."""

from __future__ import annotations

from pathlib import Path

import pytest

from . import podman_stack

pytestmark = pytest.mark.integration


@pytest.mark.timeout(900)
def test_monitoring_prometheus_and_grafana(integration_data_dir: Path):
    try:
        podman_stack.run(["./scripts/verify-synapse-postgres.sh"], timeout=900)
        podman_stack.compose("up", "-d", "prometheus", "grafana", profiles="monitoring")
        podman_stack.wait_http("http://127.0.0.1:9090/-/ready", timeout_s=180)
        podman_stack.wait_until(
            lambda: podman_stack.prometheus_target_up("synapse"),
            timeout_s=240,
            interval_s=3,
            description="Prometheus synapse target up",
        )

        podman_stack.wait_http("http://127.0.0.1:3000/api/health", timeout_s=180)
        grafana_pw = podman_stack.env_value("GRAFANA_ADMIN_PASSWORD")
        podman_stack.wait_until(
            lambda: podman_stack.grafana_prometheus_query(grafana_pw),
            timeout_s=180,
            interval_s=5,
            description="Grafana Prometheus instant query",
        )
    except Exception:
        print(podman_stack.dump_compose_logs(["prometheus", "grafana", "synapse"]))
        raise
    finally:
        podman_stack.compose_down(profiles="monitoring")
