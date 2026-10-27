"""Tests for optional NATS / Valkey bus hooks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import nats
import pytest
import redis
from nats.js.errors import BadRequestError
from redis.exceptions import RedisError

from bus_hooks import (
    BUS_DEMO_KEY,
    connect_nats_with_retry,
    fetch_latest_mention,
    run_bus_demo,
    schedule_bus_demo,
)


def _nats_mocks() -> tuple[MagicMock, AsyncMock]:
    mock_nc = MagicMock()
    mock_js = AsyncMock()
    mock_nc.jetstream.return_value = mock_js
    mock_nc.drain = AsyncMock()
    return mock_nc, mock_js


@pytest.mark.asyncio
async def test_run_bus_demo_disabled_by_default():
    with patch.dict("os.environ", {}, clear=True):
        await run_bus_demo("hello", "@bot:example.com")


@pytest.mark.asyncio
async def test_run_bus_demo_nats_publish():
    env = {
        "BUS_DEMO": "true",
        "NATS_URL": "nats://bots:secret@127.0.0.1:4222",
        "VALKEY_PASSWORD": "",
    }
    mock_nc, mock_js = _nats_mocks()

    with patch.dict("os.environ", env, clear=True):
        with patch.object(nats, "connect", AsyncMock(return_value=mock_nc)):
            await run_bus_demo("ping", "@bot:example.com")

    mock_js.add_stream.assert_awaited_once()
    mock_js.publish.assert_awaited_once()
    mock_nc.drain.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bus_demo_nats_existing_stream():
    env = {
        "BUS_DEMO": "true",
        "NATS_URL": "nats://bots:secret@127.0.0.1:4222",
    }
    mock_nc, mock_js = _nats_mocks()
    mock_js.add_stream.side_effect = BadRequestError("stream exists")

    with patch.dict("os.environ", env, clear=True):
        with patch.object(nats, "connect", AsyncMock(return_value=mock_nc)):
            await run_bus_demo("ping", "@bot:example.com")

    mock_js.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bus_demo_nats_connect_failure():
    env = {"BUS_DEMO": "true", "NATS_URL": "nats://bad:4222"}

    with patch.dict("os.environ", env, clear=True):
        with patch.object(nats, "connect", AsyncMock(side_effect=OSError("refused"))):
            await run_bus_demo("ping", "@bot:example.com")


@pytest.mark.asyncio
async def test_run_bus_demo_valkey_set_get():
    env = {
        "BUS_DEMO": "1",
        "NATS_URL": "",
        "VALKEY_HOST": "valkey",
        "VALKEY_PORT": "6379",
        "VALKEY_PASSWORD": "secret",
    }
    mock_client = MagicMock()
    mock_client.get.return_value = "stored-value"

    with patch.dict("os.environ", env, clear=True):
        with patch.object(redis, "Redis", return_value=mock_client):
            await run_bus_demo("mention body", "@bot:example.com")

    mock_client.set.assert_called_once_with(BUS_DEMO_KEY, "mention body")
    mock_client.get.assert_called_once_with(BUS_DEMO_KEY)
    mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_bus_demo_valkey_error():
    env = {"BUS_DEMO": "yes", "VALKEY_PASSWORD": "secret"}
    mock_client = MagicMock()
    mock_client.set.side_effect = RedisError("down")

    with patch.dict("os.environ", env, clear=True):
        with patch.object(redis, "Redis", return_value=mock_client):
            await run_bus_demo("x", "@b:ex")


def test_schedule_bus_demo_creates_task():
    loop = MagicMock()
    with patch("asyncio.get_running_loop", return_value=loop):
        schedule_bus_demo("hi", "@b:ex")
    loop.create_task.assert_called_once()


@pytest.mark.asyncio
async def test_connect_nats_with_retry_eventually_succeeds():
    mock_nc = MagicMock()
    with patch.object(nats, "connect", AsyncMock(side_effect=[OSError("down"), mock_nc])):
        nc = await connect_nats_with_retry("nats://127.0.0.1:4222", attempts=2, delay_s=0)
    assert nc is mock_nc


@pytest.mark.asyncio
async def test_connect_nats_with_retry_raises_after_exhausted():
    with patch.object(nats, "connect", AsyncMock(side_effect=OSError("down"))):
        with pytest.raises(OSError):
            await connect_nats_with_retry("nats://bad", attempts=2, delay_s=0)


@pytest.mark.asyncio
async def test_fetch_latest_mention_acks_message():
    mock_msg = MagicMock()
    mock_msg.data = b"payload"
    mock_msg.ack = AsyncMock()
    mock_sub = AsyncMock()
    mock_sub.fetch = AsyncMock(return_value=[mock_msg])
    mock_sub.unsubscribe = AsyncMock()
    mock_js = AsyncMock()
    mock_js.pull_subscribe = AsyncMock(return_value=mock_sub)

    got = await fetch_latest_mention(mock_js, timeout_s=1.0)
    assert got == b"payload"
    mock_msg.ack.assert_awaited_once()
    mock_sub.unsubscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bus_demo_consume_path():
    env = {
        "BUS_DEMO": "true",
        "BUS_DEMO_CONSUME": "1",
        "NATS_URL": "nats://bots:secret@127.0.0.1:4222",
    }
    mock_nc, mock_js = _nats_mocks()
    mock_js.pull_subscribe = AsyncMock()
    mock_sub = AsyncMock()
    mock_msg = MagicMock()
    mock_msg.data = b"x"
    mock_msg.ack = AsyncMock()
    mock_sub.fetch = AsyncMock(return_value=[mock_msg])
    mock_sub.unsubscribe = AsyncMock()
    mock_js.pull_subscribe.return_value = mock_sub

    with patch.dict("os.environ", env, clear=True):
        with patch.object(nats, "connect", AsyncMock(return_value=mock_nc)):
            await run_bus_demo("ping", "@bot:example.com")

    mock_js.pull_subscribe.assert_awaited()
