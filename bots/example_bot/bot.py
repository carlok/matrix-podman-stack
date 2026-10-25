#!/usr/bin/env python3
"""
Minimal Matrix bot: auto-join invites, reply when @mentioned.
Ignores messages from configured bot Matrix IDs by default to avoid loops.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional

from nio import AsyncClient, InviteMemberEvent, MatrixRoom, RoomMessageText

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("example-bot")

DEFAULT_IGNORE_LOCALPART_RE = re.compile(
    os.environ.get("BOT_IGNORE_LOCALPART_REGEX", r"^bot\d+$"),
    re.IGNORECASE,
)


async def llm_reply(prompt: str) -> str:
    """Pluggable LLM hook — replace with your provider SDK."""
    api_key = os.environ.get("LLM_PROVIDER_KEY", "").strip()
    provider = os.environ.get("LLM_PROVIDER", "stub")
    if not api_key:
        return f"(stub) Mention received: {prompt[:500]}"
    return f"({provider}) echo: {prompt[:500]}"


def ignored_senders(own_user_id: str) -> set[str]:
    ids = {own_user_id}
    extra = os.environ.get("BOT_IGNORE_MATRIX_IDS", "")
    ids.update(s.strip() for s in extra.split(",") if s.strip())
    return ids


def sender_is_ignored_bot(sender: str, own_user_id: str, server_name: str) -> bool:
    if sender in ignored_senders(own_user_id):
        return True
    if os.environ.get("BOT_IGNORE_OTHER_BOTS", "true").lower() in {"0", "false", "no"}:
        return False
    localpart = sender.split(":", 1)[0].removeprefix("@")
    if server_name and sender.endswith(f":{server_name}"):
        return bool(DEFAULT_IGNORE_LOCALPART_RE.match(localpart))
    return False


def mention_text(event: RoomMessageText, user_id: str) -> Optional[str]:
    body = event.body.strip()
    localpart = user_id.split(":", 1)[0].removeprefix("@")
    if f"@{localpart}" in body:
        return body
    display = os.environ.get("BOT_DISPLAY_NAME", localpart)
    if display and display in body:
        return body
    return None


async def main() -> None:
    homeserver = os.environ.get("MATRIX_HOMESERVER_URL", "http://127.0.0.1:8008")
    user_id = os.environ["MATRIX_USER_ID"]
    token = os.environ["MATRIX_ACCESS_TOKEN"]
    server_name = os.environ.get("SYNAPSE_SERVER_NAME", user_id.split(":", 1)[-1])

    client = AsyncClient(homeserver, user_id)
    client.access_token = token

    async def on_invite(room: MatrixRoom, event: InviteMemberEvent) -> None:
        if event.state_key != client.user_id:
            return
        log.info("Joining invited room %s", room.room_id)
        await client.join(room.room_id)

    async def on_message(room: MatrixRoom, event: RoomMessageText) -> None:
        if sender_is_ignored_bot(event.sender, user_id, server_name):
            return
        text = mention_text(event, user_id)
        if text is None:
            return
        reply = await llm_reply(text)
        await client.room_send(
            room.room_id,
            "m.room.message",
            {"msgtype": "m.text", "body": reply},
        )

    client.add_event_callback(on_invite, InviteMemberEvent)
    client.add_event_callback(on_message, RoomMessageText)

    log.info("Bot running as %s", user_id)
    await client.sync_forever(timeout=30000, full_state=True)


if __name__ == "__main__":
    asyncio.run(main())
