"""NATS JetStream consume, jsz, reconnect; Valkey KV."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bus_hooks import connect_nats_with_retry, ensure_bot_tasks_stream, fetch_latest_mention, publish_mention
from . import podman_stack

pytestmark = pytest.mark.integration


def _nats_url() -> str:
    pw = podman_stack.env_value("NATS_PASSWORD")
    return f"nats://bots:{pw}@127.0.0.1:14222"


@pytest.mark.timeout(600)
def test_jetstream_publish_consume_jsz_and_nats_restart(integration_data_dir: Path):
    try:
        podman_stack.run(["./scripts/bootstrap-bus.sh"], timeout=300)
        podman_stack.compose("up", "-d", "nats", "valkey", profiles="bus")
        podman_stack.wait_http("http://127.0.0.1:18222/healthz", timeout_s=120)
        podman_stack.wait_http("http://127.0.0.1:18222/jsz", timeout_s=60)

        async def roundtrip() -> None:
            nc = await connect_nats_with_retry(_nats_url())
            js = nc.jetstream()
            await ensure_bot_tasks_stream(js)
            await publish_mention(js, "integration", "@bot:ci.integration.test")
            got = await fetch_latest_mention(js)
            assert got is not None
            await nc.drain()

        asyncio.run(roundtrip())

        podman_stack.compose("restart", "nats", profiles="bus")
        podman_stack.wait_http("http://127.0.0.1:18222/healthz", timeout_s=120)

        async def after_restart() -> None:
            nc = await connect_nats_with_retry(_nats_url(), attempts=8, delay_s=1.0)
            js = nc.jetstream()
            info = await js.stream_info("BOT_TASKS")
            assert info.state.messages >= 1
            await nc.drain()

        asyncio.run(after_restart())
    except Exception:
        print(podman_stack.dump_compose_logs(["nats", "valkey"]))
        raise
    finally:
        podman_stack.compose_down(profiles="bus")


@pytest.mark.timeout(300)
def test_valkey_kv_survives_restart(integration_data_dir: Path):
    import redis

    pw = podman_stack.env_value("VALKEY_PASSWORD")
    try:
        podman_stack.run(["./scripts/bootstrap-bus.sh"], timeout=300)
        podman_stack.compose("up", "-d", "valkey", profiles="bus")
        ready = False
        for _ in range(40):
            try:
                client = redis.Redis(host="127.0.0.1", port=16379, password=pw, decode_responses=True)
                client.ping()
                client.close()
                ready = True
                break
            except redis.RedisError:
                __import__("time").sleep(2)
        assert ready, "Valkey did not become ready"
        client = redis.Redis(host="127.0.0.1", port=16379, password=pw, decode_responses=True)
        client.set("matrix:integration:marker", "valkey-ok")
        client.close()
        podman_stack.compose("restart", "valkey", profiles="bus")
        for _ in range(40):
            try:
                client = redis.Redis(host="127.0.0.1", port=16379, password=pw, decode_responses=True)
                assert client.get("matrix:integration:marker") == "valkey-ok"
                client.close()
                return
            except redis.RedisError:
                __import__("time").sleep(2)
        raise AssertionError("Valkey did not recover after restart")
    except Exception:
        print(podman_stack.dump_compose_logs(["valkey"]))
        raise
    finally:
        podman_stack.compose_down(profiles="bus")
