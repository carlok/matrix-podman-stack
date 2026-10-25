"""Optional NATS JetStream + Valkey hooks for the example bot (env-gated)."""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("example-bot.bus")

BUS_DEMO_KEY = "matrix:bot:last_mention"


async def run_bus_demo(mention_text: str, bot_user_id: str) -> None:
    if os.environ.get("BUS_DEMO", "").lower() not in {"1", "true", "yes"}:
        return

    nats_url = os.environ.get("NATS_URL", "").strip()
    valkey_host = os.environ.get("VALKEY_HOST", "valkey").strip()
    valkey_port = int(os.environ.get("VALKEY_PORT", "6379"))
    valkey_password = os.environ.get("VALKEY_PASSWORD", "")

    if nats_url:
        try:
            import nats

            nc = await nats.connect(nats_url)
            js = nc.jetstream()
            try:
                await js.add_stream(name="BOT_TASKS", subjects=["bot.tasks.>"])
            except Exception:
                pass
            payload = f"{bot_user_id}:{mention_text[:200]}".encode()
            await js.publish("bot.tasks.mention", payload)
            await nc.close()
            log.info("Published mention event to NATS JetStream")
        except Exception as exc:
            log.warning("NATS publish skipped: %s", exc)

    if valkey_password:
        try:
            import redis

            client = redis.Redis(
                host=valkey_host,
                port=valkey_port,
                password=valkey_password,
                decode_responses=True,
            )
            client.set(BUS_DEMO_KEY, mention_text[:500])
            log.info("Valkey %s=%r", BUS_DEMO_KEY, client.get(BUS_DEMO_KEY)[:40])
        except Exception as exc:
            log.warning("Valkey write skipped: %s", exc)


def schedule_bus_demo(mention_text: str, bot_user_id: str) -> None:
    asyncio.get_event_loop().create_task(run_bus_demo(mention_text, bot_user_id))
