"""Tests for optional NATS / Valkey bus hooks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import nats
import pytest
import redis
from nats.js.errors import BadRequestError
from redis.exceptions import RedisError

from bus_hooks import BUS_DEMO_KEY, run_bus_demo, schedule_bus_demo


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
