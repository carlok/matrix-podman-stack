"""Optional compose profiles: Element, Telegram, Qdrant, Ollama."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from . import podman_stack

pytestmark = pytest.mark.integration


@pytest.mark.timeout(600)
def test_element_serves_config(integration_data_dir: Path):
    try:
        podman_stack.run(["./scripts/verify-synapse-postgres.sh"], timeout=900)
        podman_stack.compose("up", "-d", "element")
        podman_stack.wait_http("http://127.0.0.1:8080/", timeout_s=120)
        cfg = json.loads((integration_data_dir / "element" / "config.json").read_text())
        assert "m.homeserver" in cfg
        assert cfg["m.homeserver"]["base_url"].startswith("http")
    except Exception:
        print(podman_stack.dump_compose_logs(["element", "synapse"]))
        raise
    finally:
        podman_stack.compose_down()


@pytest.mark.timeout(900)
def test_telegram_bridge_registers_appservice(integration_data_dir: Path):
    try:
        podman_stack.run(["./scripts/verify-synapse-postgres.sh"], timeout=900)
        podman_stack.run(["./scripts/bootstrap-telegram.sh"], timeout=300)
        podman_stack.compose("up", "-d", "postgres-telegram", "mautrix-telegram", profiles="telegram")
        def registration_present() -> bool:
            return "telegram-registration.yaml" in (integration_data_dir / "synapse" / "homeserver.yaml").read_text()

        podman_stack.wait_until(registration_present, timeout_s=240, description="telegram appservice registration")
        reg = integration_data_dir / "synapse" / "telegram-registration.yaml"
        assert reg.is_file()
        # Bridge may exit-loop without Telegram login; container should exist or have started.
        proc = podman_stack.compose("ps", profiles="telegram", check=False)
        assert "mautrix-telegram" in proc.stdout or "postgres-telegram" in proc.stdout
    except Exception:
        print(podman_stack.dump_compose_logs(["mautrix-telegram", "postgres-telegram", "synapse"]))
        raise
    finally:
        podman_stack.compose_down(profiles="telegram")


@pytest.mark.timeout(600)
def test_qdrant_collection_upsert_search(integration_data_dir: Path):
    api_key = podman_stack.env_value("QDRANT_API_KEY")
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    try:
        podman_stack.run(["./scripts/bootstrap-vectors.sh"], timeout=300)
        podman_stack.wait_http(
            "http://127.0.0.1:16333/healthz",
            timeout_s=180,
            headers={"api-key": api_key},
        )
        put = urllib.request.Request(
            "http://127.0.0.1:16333/collections/ci_probe",
            data=json.dumps({"vectors": {"size": 4, "distance": "Cosine"}}).encode(),
            headers=headers,
            method="PUT",
        )
        urllib.request.urlopen(put, timeout=30)
        upsert = urllib.request.Request(
            "http://127.0.0.1:16333/collections/ci_probe/points",
            data=json.dumps(
                {"points": [{"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {"tag": "ci"}}]}
            ).encode(),
            headers=headers,
            method="PUT",
        )
        urllib.request.urlopen(upsert, timeout=30)
        search = urllib.request.Request(
            "http://127.0.0.1:16333/collections/ci_probe/points/search",
            data=json.dumps({"vector": [0.1, 0.2, 0.3, 0.4], "limit": 1}).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(search, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        assert body["result"][0]["id"] == 1
    except Exception:
        print(podman_stack.dump_compose_logs(["qdrant"]))
        raise
    finally:
        podman_stack.compose_down(profiles="vectors")


@pytest.mark.timeout(600)
def test_ollama_api_up(integration_data_dir: Path):
    try:
        podman_stack.compose("up", "-d", "ollama", profiles="llm")
        podman_stack.wait_http("http://127.0.0.1:11434/api/tags", timeout_s=180)
    except Exception:
        print(podman_stack.dump_compose_logs(["ollama"]))
        raise
    finally:
        podman_stack.compose_down(profiles="llm")
