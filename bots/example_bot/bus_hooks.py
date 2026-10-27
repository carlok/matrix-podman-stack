"""Optional NATS JetStream + Valkey hooks for the example bot (env-gated)."""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("example-bot.bus")

BUS_DEMO_KEY = "matrix:bot:last_mention"
BOT_TASKS_STREAM = "BOT_TASKS"
MENTION_SUBJECT = "bot.tasks.mention"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def _nats_reconnect_attempts() -> int:
    raw = os.environ.get("NATS_RECONNECT_ATTEMPTS", "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _nats_reconnect_delay() -> float:
    raw = os.environ.get("NATS_RECONNECT_DELAY", "0.5").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.5


async def connect_nats_with_retry(
    nats_url: str,
    *,
    attempts: int | None = None,
    delay_s: float | None = None,
):
    """Connect to NATS with bounded retries (used after broker restarts)."""
    import nats

    tries = attempts if attempts is not None else _nats_reconnect_attempts()
    delay = delay_s if delay_s is not None else _nats_reconnect_delay()
    last_exc: BaseException | None = None
    for attempt in range(tries):
        try:
            return await nats.connect(nats_url)
        except (OSError, TimeoutError, ValueError) as exc:
            last_exc = exc
            if attempt + 1 < tries:
                log.debug("NATS connect attempt %s failed: %s", attempt + 1, exc)
                await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def ensure_bot_tasks_stream(js) -> None:
    from nats.js.errors import BadRequestError

    try:
        await js.add_stream(name=BOT_TASKS_STREAM, subjects=["bot.tasks.>"])
    except BadRequestError:
        log.debug("JetStream %s stream already exists", BOT_TASKS_STREAM)


async def publish_mention(js, mention_text: str, bot_user_id: str) -> None:
    payload = f"{bot_user_id}:{mention_text[:200]}".encode()
    await js.publish(MENTION_SUBJECT, payload)


async def fetch_latest_mention(js, *, timeout_s: float = 5.0) -> bytes | None:
    """Pull the newest message from the mention subject (integration / BUS_DEMO_CONSUME)."""
    sub = await js.pull_subscribe(MENTION_SUBJECT, durable=None, stream=BOT_TASKS_STREAM)
    try:
        msgs = await sub.fetch(1, timeout=timeout_s)
        if not msgs:
            return None
        data = msgs[0].data
        await msgs[0].ack()
        return data
    finally:
        await sub.unsubscribe()


async def run_bus_demo(mention_text: str, bot_user_id: str) -> None:
    if not _truthy("BUS_DEMO"):
        return

    nats_url = os.environ.get("NATS_URL", "").strip()
    valkey_host = os.environ.get("VALKEY_HOST", "valkey").strip()
    valkey_port = int(os.environ.get("VALKEY_PORT", "6379"))
    valkey_password = os.environ.get("VALKEY_PASSWORD", "")

    if nats_url:
        try:
            nc = await connect_nats_with_retry(nats_url)
            try:
                js = nc.jetstream()
                await ensure_bot_tasks_stream(js)
                await publish_mention(js, mention_text, bot_user_id)
                log.info("Published mention event to NATS JetStream")
                if _truthy("BUS_DEMO_CONSUME"):
                    got = await fetch_latest_mention(js)
                    if got is None:
                        log.warning("BUS_DEMO_CONSUME: no JetStream message fetched")
                    else:
                        log.info("BUS_DEMO_CONSUME: verified message (%d bytes)", len(got))
            finally:
                await nc.drain()
        except (ImportError, OSError, TimeoutError, ValueError) as exc:
            log.warning("NATS publish skipped: %s", exc)

    if valkey_password:
        try:
            import redis
            from redis.exceptions import RedisError

            client = redis.Redis(
                host=valkey_host,
                port=valkey_port,
                password=valkey_password,
                decode_responses=True,
            )
            try:
                client.set(BUS_DEMO_KEY, mention_text[:500])
                stored = client.get(BUS_DEMO_KEY)
                preview = (stored or "")[:40]
                log.info("Valkey %s=%r", BUS_DEMO_KEY, preview)
            finally:
                client.close()
        except (ImportError, OSError, ValueError, RedisError) as exc:
            log.warning("Valkey write skipped: %s", exc)


def schedule_bus_demo(mention_text: str, bot_user_id: str) -> None:
    loop = asyncio.get_running_loop()
    loop.create_task(run_bus_demo(mention_text, bot_user_id))
