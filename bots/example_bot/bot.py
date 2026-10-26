#!/usr/bin/env python3
"""
Minimal Matrix bot: auto-join invites, reply when @mentioned.
Optional master/worker duo mode (BOT_DUO_ENABLED) for bounded bot-to-bot threads.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

from nio import (
    AsyncClient,
    InviteMemberEvent,
    MatrixRoom,
    RoomMessageText,
    SyncResponse,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bus_hooks import run_bus_demo
from duo import DuoConversation, DuoSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("example-bot")

DEFAULT_IGNORE_LOCALPART_RE = re.compile(
    os.environ.get("BOT_IGNORE_LOCALPART_REGEX", r"^bot\d+$"),
    re.IGNORECASE,
)


async def llm_reply(prompt: str) -> str:
    """Pluggable LLM hook — replace with your provider SDK."""
    provider = os.environ.get("LLM_PROVIDER", "stub").lower()
    if provider == "ollama":
        import aiohttp

        base = os.environ.get("OLLAMA_URL", "http://ollama:11434").rstrip("/")
        model = os.environ.get("OLLAMA_MODEL", "tinyllama")
        payload = {"model": model, "prompt": prompt, "stream": False}
        timeout = aiohttp.ClientTimeout(total=120)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(f"{base}/api/generate", json=payload) as resp,
            ):
                data = await resp.json()
                return str(data.get("response", ""))[:2000] or "(ollama: empty response)"
        except (TimeoutError, aiohttp.ClientError, ValueError) as exc:
            return f"(ollama error) {exc}"

    api_key = os.environ.get("LLM_PROVIDER_KEY", "").strip()
    if not api_key:
        return f"(stub) Mention received: {prompt[:500]}"
    return f"({provider}) echo: {prompt[:500]}"


def ignored_senders(own_user_id: str) -> set[str]:
    ids = {own_user_id}
    extra = os.environ.get("BOT_IGNORE_MATRIX_IDS", "")
    ids.update(s.strip() for s in extra.split(",") if s.strip())
    return ids


def duo_enabled() -> bool:
    return os.environ.get("BOT_DUO_ENABLED", "").lower() in {"1", "true", "yes"}


def sender_is_ignored_bot(sender: str, own_user_id: str, server_name: str) -> bool:
    if sender in ignored_senders(own_user_id):
        return True
    if duo_enabled():
        peers = {
            s.strip()
            for s in os.environ.get("BOT_DUO_PEER_MXIDS", "").split(",")
            if s.strip()
        }
        if sender in peers:
            return False
    if os.environ.get("BOT_IGNORE_OTHER_BOTS", "true").lower() in {"0", "false", "no"}:
        return False
    localpart = sender.split(":", 1)[0].removeprefix("@")
    if server_name and sender.endswith(f":{server_name}"):
        return bool(DEFAULT_IGNORE_LOCALPART_RE.match(localpart))
    return False


def is_bot_localpart(sender: str, server_name: str) -> bool:
    localpart = sender.split(":", 1)[0].removeprefix("@")
    if server_name and sender.endswith(f":{server_name}"):
        return bool(DEFAULT_IGNORE_LOCALPART_RE.match(localpart))
    return False


def mention_text(event: RoomMessageText, user_id: str) -> str | None:
    body = event.body.strip()
    localpart = user_id.split(":", 1)[0].removeprefix("@")
    if f"@{localpart}" in body:
        return body
    display = os.environ.get("BOT_DISPLAY_NAME", localpart)
    if display and display in body:
        return body
    return None


def body_mentions_user(body: str, user_id: str) -> bool:
    localpart = user_id.split(":", 1)[0].removeprefix("@")
    return f"@{localpart}" in body or user_id in body


async def main() -> None:
    homeserver = os.environ.get("MATRIX_HOMESERVER_URL", "http://127.0.0.1:8008")
    user_id = os.environ["MATRIX_USER_ID"]
    token = os.environ["MATRIX_ACCESS_TOKEN"]
    server_name = os.environ.get("SYNAPSE_SERVER_NAME", user_id.split(":", 1)[-1])

    duo_settings = DuoSettings.from_env()
    duo = DuoConversation(duo_settings, user_id) if duo_settings.enabled else None
    started_ms = int(time.time() * 1000)

    client = AsyncClient(homeserver, user_id)
    client.access_token = token

    async def on_invite(room: MatrixRoom, event: InviteMemberEvent) -> None:
        if event.state_key != client.user_id:
            return
        log.info("Joining invited room %s", room.room_id)
        await client.join(room.room_id)

    def event_is_live(event: RoomMessageText) -> bool:
        ts = getattr(event, "server_timestamp", None)
        if ts is None and hasattr(event, "source"):
            ts = event.source.get("origin_server_ts")
        if ts is None:
            return True
        return int(ts) >= started_ms - 10_000

    async def on_message(room: MatrixRoom, event: RoomMessageText) -> None:
        if event.sender == user_id:
            return
        if getattr(event, "msgtype", "m.text") != "m.text":
            return
        if not event_is_live(event):
            return

        body = event.body.strip()
        mentioned = body_mentions_user(body, user_id)
        is_bot = is_bot_localpart(event.sender, server_name)

        if duo and duo_settings.enabled:
            if sender_is_ignored_bot(event.sender, user_id, server_name) and not mentioned:
                return
            duo_reply = duo.process(
                room.room_id,
                event.event_id,
                event.sender,
                body,
                mentioned,
                is_bot,
            )
            if duo_reply:
                await client.room_send(
                    room.room_id,
                    "m.room.message",
                    {"msgtype": duo_reply.msgtype, "body": duo_reply.body},
                )
                if os.environ.get("BOT_ONE_SHOT", "").lower() in {"1", "true", "yes"}:
                    await client.close()
                return
            if duo_settings.enabled and duo_settings.role in {"master", "worker"}:
                return

        if sender_is_ignored_bot(event.sender, user_id, server_name):
            return
        text = mention_text(event, user_id)
        if text is None:
            return
        await run_bus_demo(text, user_id)
        reply = await llm_reply(text)
        await client.room_send(
            room.room_id,
            "m.room.message",
            {"msgtype": "m.text", "body": reply},
        )
        if os.environ.get("BOT_ONE_SHOT", "").lower() in {"1", "true", "yes"}:
            log.info("One-shot reply sent; exiting")
            await client.close()

    async def join_invites_on_sync(response: SyncResponse) -> None:
        for room_id in response.rooms.invite:
            log.info("Joining invited room %s (sync invite)", room_id)
            await client.join(room_id)

    client.add_event_callback(on_invite, InviteMemberEvent)
    client.add_event_callback(on_message, RoomMessageText)
    client.add_response_callback(join_invites_on_sync, SyncResponse)

    log.info(
        "Bot running as %s (duo=%s role=%s)",
        user_id,
        duo_settings.enabled,
        duo_settings.role or "-",
    )
    await client.sync_forever(timeout=30000, full_state=False)


if __name__ == "__main__":
    asyncio.run(main())
