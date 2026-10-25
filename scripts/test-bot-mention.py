#!/usr/bin/env python3
"""Bounded smoke test: bot replies to human @mention, ignores other bots."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path


def api(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def wait_for_member(
    base: str, admin_token: str, room_id: str, user_id: str, timeout_s: float
) -> bool:
    deadline = time.time() + timeout_s
    enc_room = urllib.parse.quote(room_id, safe="")
    while time.time() < deadline:
        state = api(
            "GET",
            f"{base}/_matrix/client/v3/rooms/{enc_room}/joined_members",
            admin_token,
        )
        if user_id in state.get("joined", {}):
            return True
        time.sleep(0.5)
    return False


def wait_for_reply(
    base: str, admin_token: str, room_id: str, sender: str, timeout_s: float
) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        enc_room = urllib.parse.quote(room_id, safe="")
        events = api(
            "GET",
            f"{base}/_matrix/client/v3/rooms/{enc_room}/messages?dir=b&limit=20",
            admin_token,
        )
        for item in events.get("chunk", []):
            if item.get("type") != "m.room.message":
                continue
            if item.get("sender") == sender:
                return item.get("content", {}).get("body", "")
        time.sleep(0.5)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--homeserver", default=os.environ.get("SYNAPSE_INTERNAL_URL", "http://127.0.0.1:8008"))
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--admin-user", default=os.environ.get("TEST_ADMIN_USER", "admin"))
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--bot-user-id", required=True)
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--bot-localpart", required=True)
    parser.add_argument("--bot-display-name", default="")
    parser.add_argument("--second-bot-user-id", default="")
    parser.add_argument("--second-bot-token", default="")
    parser.add_argument("--second-bot-localpart", default="")
    parser.add_argument("--bot-script", type=Path, required=True)
    parser.add_argument("--venv-python", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    base = args.homeserver.rstrip("/")
    admin_token = os.environ.get("SYNAPSE_ADMIN_ACCESS_TOKEN", "").strip()
    if not admin_token:
        token_file = Path(os.environ.get("BOT_TOKENS_FILE", "data/bots/tokens.env")).parent / "admin.token"
        if token_file.is_file():
            admin_token = token_file.read_text().strip()
    if not admin_token:
        admin_token = api(
            "POST",
            f"{base}/_matrix/client/v3/login",
            body={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": args.admin_user},
                "password": args.admin_password,
            },
        )["access_token"]

    env = os.environ.copy()
    env.update(
        {
            "MATRIX_HOMESERVER_URL": base,
            "MATRIX_USER_ID": args.bot_user_id,
            "MATRIX_ACCESS_TOKEN": args.bot_token,
            "BOT_DISPLAY_NAME": args.bot_display_name or args.bot_localpart,
            "SYNAPSE_SERVER_NAME": args.server_name,
            "BOT_ONE_SHOT": "true",
            "BOT_IGNORE_OTHER_BOTS": "true",
        }
    )
    ignore = os.environ.get("BOT_IGNORE_MATRIX_IDS", "")
    if ignore:
        env["BOT_IGNORE_MATRIX_IDS"] = ignore

    bot_proc = subprocess.Popen(
        [str(args.venv_python), str(args.bot_script)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        time.sleep(2)
        room_id = api(
            "POST",
            f"{base}/_matrix/client/v3/createRoom",
            admin_token,
            {
                "preset": "private_chat",
                "invite": [args.bot_user_id],
                "name": "bot-smoke-test",
            },
        )["room_id"]
        enc_room = urllib.parse.quote(room_id, safe="")

        if args.second_bot_user_id:
            api(
                "POST",
                f"{base}/_matrix/client/v3/rooms/{enc_room}/invite",
                admin_token,
                {"user_id": args.second_bot_user_id},
            )
            if args.second_bot_token:
                api(
                    "POST",
                    f"{base}/_matrix/client/v3/rooms/{enc_room}/join",
                    args.second_bot_token,
                    {},
                )

        if not wait_for_member(base, admin_token, room_id, args.bot_user_id, 20):
            out = bot_proc.stdout.read().decode(errors="replace") if bot_proc.stdout else ""
            raise SystemExit(f"FAIL: bot never joined room\n{out[-2000:]}")
        api("POST", f"{base}/_matrix/client/v3/rooms/{enc_room}/join", admin_token, {})
        time.sleep(1)

        txn = str(int(time.time() * 1000))
        if args.second_bot_token and args.second_bot_localpart:
            api(
                "PUT",
                f"{base}/_matrix/client/v3/rooms/{enc_room}/send/m.room.message/{txn}b2",
                args.second_bot_token,
                {
                    "msgtype": "m.text",
                    "body": f"From bot2 @{args.bot_localpart} please ignore",
                },
            )
            time.sleep(3)
            if wait_for_reply(base, admin_token, room_id, args.bot_user_id, 5):
                raise SystemExit("FAIL: bot replied to another bot's mention")

        txn2 = str(int(time.time() * 1000))
        api(
            "PUT",
            f"{base}/_matrix/client/v3/rooms/{enc_room}/send/m.room.message/{txn2}admin",
            admin_token,
            {
                "msgtype": "m.text",
                "body": f"Hello @{args.bot_localpart} ping",
            },
        )

        reply = wait_for_reply(base, admin_token, room_id, args.bot_user_id, args.timeout)
        if not reply:
            raise SystemExit("FAIL: bot did not reply to admin mention")
        print(f"OK: bot replied: {reply[:120]}")
    finally:
        bot_proc.terminate()
        try:
            bot_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bot_proc.kill()


if __name__ == "__main__":
    main()
