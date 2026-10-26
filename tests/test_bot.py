from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bot import (
    body_mentions_user,
    duo_enabled,
    event_is_live,
    handle_room_message_text,
    ignored_senders,
    is_bot_localpart,
    llm_reply,
    mention_text,
    sender_is_ignored_bot,
)
from duo import DuoConversation, DuoSettings


@pytest.fixture(autouse=True)
def _clean_bot_env(monkeypatch: pytest.MonkeyPatch):
    for key in list(os.environ):
        if key.startswith(("BOT_", "LLM_", "OLLAMA_", "MATRIX_", "SYNAPSE_")):
            monkeypatch.delenv(key, raising=False)


def test_ignored_senders():
    os.environ["BOT_IGNORE_MATRIX_IDS"] = "@other:ex, @x:ex"
    ids = ignored_senders("@self:ex")
    assert "@self:ex" in ids
    assert "@other:ex" in ids


def test_duo_enabled_truthy():
    os.environ["BOT_DUO_ENABLED"] = "yes"
    assert duo_enabled() is True


def test_sender_is_ignored_bot_own_user_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOT_IGNORE_MATRIX_IDS", "@blocked:example.com")
    assert sender_is_ignored_bot("@blocked:example.com", "@bot1:example.com", "example.com") is True


def test_sender_is_ignored_bot_with_duo_peer_exception():
    os.environ["BOT_DUO_ENABLED"] = "true"
    os.environ["BOT_DUO_PEER_MXIDS"] = "@bot2:example.com"
    assert sender_is_ignored_bot("@bot2:example.com", "@bot1:example.com", "example.com") is False
    assert sender_is_ignored_bot("@bot3:example.com", "@bot1:example.com", "example.com") is True


def test_ignore_other_bots_disabled():
    os.environ["BOT_IGNORE_OTHER_BOTS"] = "false"
    assert sender_is_ignored_bot("@bot9:example.com", "@bot1:example.com", "example.com") is False


def test_is_bot_localpart():
    assert is_bot_localpart("@bot1:example.com", "example.com") is True
    assert is_bot_localpart("@human:example.com", "example.com") is False
    assert is_bot_localpart("@bot1:other.com", "example.com") is False


def test_ignored_sender_wrong_server():
    assert sender_is_ignored_bot("@bot1:other.com", "@bot1:example.com", "example.com") is False


def test_body_mentions_user():
    assert body_mentions_user("hi @bot1", "@bot1:example.com") is True
    assert body_mentions_user("@bot1:example.com ping", "@bot1:example.com") is True
    assert body_mentions_user("no mention", "@bot1:example.com") is False


def test_mention_text_localpart_and_display():
    event = SimpleNamespace(body="hello @bot1 there")
    assert mention_text(event, "@bot1:example.com") == "hello @bot1 there"
    os.environ["BOT_DISPLAY_NAME"] = "Helper Bot"
    event2 = SimpleNamespace(body="ping Helper Bot")
    assert mention_text(event2, "@bot1:example.com") == "ping Helper Bot"
    assert mention_text(SimpleNamespace(body="nope"), "@bot1:example.com") is None


def test_event_is_live():
    now = 1_000_000
    old = SimpleNamespace(server_timestamp=now - 20_000, source={})
    new = SimpleNamespace(server_timestamp=now - 1_000, source={})
    assert event_is_live(old, now) is False
    assert event_is_live(new, now) is True
    assert event_is_live(SimpleNamespace(source={}), now) is True


@pytest.mark.asyncio
async def test_llm_reply_stub():
    reply = await llm_reply("hello")
    assert "(stub)" in reply


@pytest.mark.asyncio
async def test_llm_reply_with_provider_key():
    os.environ["LLM_PROVIDER_KEY"] = "secret"
    os.environ["LLM_PROVIDER"] = "custom"
    reply = await llm_reply("hi")
    assert "(custom)" in reply


@pytest.mark.asyncio
async def test_llm_reply_ollama_mocked():
    os.environ["LLM_PROVIDER"] = "ollama"

    class FakeResp:
        async def json(self):
            return {"response": "ok from model"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class FakeSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, *a, **k):
            return FakeResp()

    with patch("aiohttp.ClientSession", FakeSession):
        reply = await llm_reply("prompt")
    assert "ok from model" in reply


@pytest.mark.asyncio
async def test_handle_mention_path_sends_reply(tmp_path):
    client = AsyncMock()
    room = SimpleNamespace(room_id="!r:ex")
    event = SimpleNamespace(
        sender="@human:example.com",
        event_id="e1",
        body="hey @bot1",
        msgtype="m.text",
        server_timestamp=9_999_999_999_999,
    )
    settings = DuoSettings(
        enabled=False,
        role="",
        peer_mxids=set(),
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=tmp_path,
    )
    with patch("bot.run_bus_demo", AsyncMock()):
        await handle_room_message_text(
            client,
            room,
            event,
            user_id="@bot1:example.com",
            server_name="example.com",
            duo=None,
            duo_settings=settings,
            started_ms=9_999_999_999_000,
        )
    client.room_send.assert_awaited_once()
    assert "(stub)" in client.room_send.await_args[0][2]["body"]


@pytest.mark.asyncio
async def test_handle_duo_master_reply(tmp_path):
    client = AsyncMock()
    room = SimpleNamespace(room_id="!r:ex")
    settings = DuoSettings(
        enabled=True,
        role="master",
        peer_mxids={"@bot2:example.com"},
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=tmp_path / "duo",
    )
    duo = DuoConversation(settings, "@bot1:example.com")
    event = SimpleNamespace(
        sender="@admin:example.com",
        event_id="e1",
        body="!discuss topic",
        msgtype="m.text",
        server_timestamp=9_999_999_999_999,
    )
    await handle_room_message_text(
        client,
        room,
        event,
        user_id="@bot1:example.com",
        server_name="example.com",
        duo=duo,
        duo_settings=settings,
        started_ms=9_999_999_999_000,
    )
    client.room_send.assert_awaited_once()
    assert "topic:" in client.room_send.await_args[0][2]["body"]


@pytest.mark.asyncio
async def test_llm_reply_ollama_error():
    os.environ["LLM_PROVIDER"] = "ollama"

    class FakeSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, *a, **k):
            import aiohttp

            class BadCtx:
                async def __aenter__(self):
                    raise aiohttp.ClientError("down")

                async def __aexit__(self, *args):
                    return None

            return BadCtx()

    with patch("aiohttp.ClientSession", FakeSession):
        reply = await llm_reply("x")
    assert "(ollama error)" in reply


@pytest.mark.asyncio
async def test_handle_one_shot_closes_client(tmp_path):
    os.environ["BOT_ONE_SHOT"] = "true"
    client = AsyncMock()
    room = SimpleNamespace(room_id="!r:ex")
    event = SimpleNamespace(
        sender="@human:example.com",
        event_id="e1",
        body="hey @bot1",
        msgtype="m.text",
        server_timestamp=9_999_999_999_999,
    )
    settings = DuoSettings(
        enabled=False,
        role="",
        peer_mxids=set(),
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=tmp_path,
    )
    with patch("bot.run_bus_demo", AsyncMock()):
        await handle_room_message_text(
            client,
            room,
            event,
            user_id="@bot1:example.com",
            server_name="example.com",
            duo=None,
            duo_settings=settings,
            started_ms=9_999_999_999_000,
        )
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_duo_worker_swallows_non_duo_mention(tmp_path):
    client = AsyncMock()
    room = SimpleNamespace(room_id="!r:ex")
    settings = DuoSettings(
        enabled=True,
        role="worker",
        peer_mxids={"@bot1:example.com"},
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=tmp_path / "duo",
    )
    duo = DuoConversation(settings, "@bot2:example.com")
    event = SimpleNamespace(
        sender="@human:example.com",
        event_id="e1",
        body="@bot2 hello",
        msgtype="m.text",
        server_timestamp=9_999_999_999_999,
    )
    await handle_room_message_text(
        client,
        room,
        event,
        user_id="@bot2:example.com",
        server_name="example.com",
        duo=duo,
        duo_settings=settings,
        started_ms=9_999_999_999_000,
    )
    client.room_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_skips_non_text():
    client = AsyncMock()
    room = SimpleNamespace(room_id="!r:ex")
    settings = DuoSettings(
        enabled=False,
        role="",
        peer_mxids=set(),
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=MagicMock(),
    )
    event = SimpleNamespace(
        sender="@human:example.com",
        event_id="e",
        body="x",
        msgtype="m.image",
        server_timestamp=9_999_999_999_999,
    )
    await handle_room_message_text(
        client,
        room,
        event,
        user_id="@bot1:example.com",
        server_name="example.com",
        duo=None,
        duo_settings=settings,
        started_ms=9_999_999_999_000,
    )
    client.room_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_wires_client(monkeypatch):
    monkeypatch.setenv("MATRIX_USER_ID", "@bot1:example.com")
    monkeypatch.setenv("MATRIX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("SYNAPSE_SERVER_NAME", "example.com")
    monkeypatch.setenv("BOT_DUO_ENABLED", "false")

    client = MagicMock()
    client.user_id = "@bot1:example.com"
    client.sync_forever = AsyncMock()
    client.add_event_callback = MagicMock()
    client.add_response_callback = MagicMock()

    with patch("bot.AsyncClient", return_value=client):
        from bot import main

        await main()

    client.sync_forever.assert_awaited_once()
    assert client.add_event_callback.call_count == 2


@pytest.mark.asyncio
async def test_join_invites_on_sync_callback(monkeypatch):
    monkeypatch.setenv("MATRIX_USER_ID", "@bot1:example.com")
    monkeypatch.setenv("MATRIX_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("SYNAPSE_SERVER_NAME", "example.com")

    client = MagicMock()
    client.user_id = "@bot1:example.com"
    client.join = AsyncMock()
    client.sync_forever = AsyncMock(side_effect=asyncio.CancelledError)
    client.add_event_callback = MagicMock()
    client.add_response_callback = MagicMock()

    response = MagicMock()
    response.rooms.invite = {"!inv:ex"}

    with patch("bot.AsyncClient", return_value=client):
        from bot import main

        try:
            await main()
        except asyncio.CancelledError:
            pass

    cb = client.add_response_callback.call_args[0][0]
    await cb(response)
    client.join.assert_awaited_with("!inv:ex")


@pytest.mark.asyncio
async def test_on_invite_joins_self(monkeypatch):
    monkeypatch.setenv("MATRIX_USER_ID", "@bot1:example.com")
    monkeypatch.setenv("MATRIX_ACCESS_TOKEN", "tok")

    client = MagicMock()
    client.user_id = "@bot1:example.com"
    client.join = AsyncMock()
    client.sync_forever = AsyncMock(side_effect=asyncio.CancelledError)
    client.add_event_callback = MagicMock()
    client.add_response_callback = MagicMock()

    with patch("bot.AsyncClient", return_value=client):
        from bot import main

        try:
            await main()
        except asyncio.CancelledError:
            pass

    invite_cb = client.add_event_callback.call_args_list[0][0][0]
    room = MagicMock(room_id="!r:ex")
    event = MagicMock(state_key="@bot1:example.com")
    await invite_cb(room, event)
    client.join.assert_awaited_with("!r:ex")


@pytest.mark.asyncio
async def test_handle_skips_own_and_stale():
    client = AsyncMock()
    room = SimpleNamespace(room_id="!r:ex")
    settings = DuoSettings(
        enabled=False,
        role="",
        peer_mxids=set(),
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=MagicMock(),
    )
    own = SimpleNamespace(
        sender="@bot1:example.com",
        event_id="e",
        body="@bot1",
        msgtype="m.text",
        server_timestamp=100,
    )
    await handle_room_message_text(
        client,
        room,
        own,
        user_id="@bot1:example.com",
        server_name="example.com",
        duo=None,
        duo_settings=settings,
        started_ms=1_000_000,
    )
    client.room_send.assert_not_awaited()
