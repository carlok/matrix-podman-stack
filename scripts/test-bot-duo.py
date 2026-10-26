#!/usr/bin/env python3
"""E2E: two bots in duo mode stop at turn cap and honor [DONE]."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matrix_testutil import api, fetch_messages, login, wait_member


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--homeserver", default=os.environ.get("SYNAPSE_INTERNAL_URL", "http://127.0.0.1:8008"))
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--master-user-id", required=True)
    parser.add_argument("--master-token", required=True)
    parser.add_argument("--worker-user-id", required=True)
    parser.add_argument("--worker-token", required=True)
    parser.add_argument("--bot-script", type=Path, required=True)
    parser.add_argument("--venv-python", type=Path, required=True)
    parser.add_argument("--max-turns", type=int, default=4)
    parser.add_argument("--stop-marker", default="[DONE]")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    base = args.homeserver.rstrip("/")
    admin_token = login(base, os.environ.get("TEST_ADMIN_USER", "admin"), args.admin_password)

    master_env = os.environ.copy()
    master_env.update(
        {
            "MATRIX_HOMESERVER_URL": base,
            "MATRIX_USER_ID": args.master_user_id,
            "MATRIX_ACCESS_TOKEN": args.master_token,
            "SYNAPSE_SERVER_NAME": args.server_name,
            "BOT_DUO_ENABLED": "true",
            "BOT_DUO_ROLE": "master",
            "BOT_DUO_PEER_MXIDS": args.worker_user_id,
            "BOT_IGNORE_OTHER_BOTS": "false",
            "BOT_MAX_TURNS": str(args.max_turns),
            "BOT_DUO_STOP_MARKER": args.stop_marker,
            "BOT_DUO_COOLDOWN_SECONDS": "0",
            "BOT_DUO_STATE_DIR": os.environ.get("BOT_DUO_STATE_DIR", "data/bots/duo-state"),
        }
    )
    worker_env = master_env.copy()
    worker_env.update(
        {
            "MATRIX_USER_ID": args.worker_user_id,
            "MATRIX_ACCESS_TOKEN": args.worker_token,
            "BOT_DUO_ROLE": "worker",
            "BOT_DUO_PEER_MXIDS": args.master_user_id,
        }
    )

    master_proc = subprocess.Popen(
        [str(args.venv_python), str(args.bot_script)],
        env=master_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    worker_proc = subprocess.Popen(
        [str(args.venv_python), str(args.bot_script)],
        env=worker_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        state_dir = Path(master_env.get("BOT_DUO_STATE_DIR", "data/bots/duo-state"))
        if state_dir.is_dir():
            for path in state_dir.glob("*.json"):
                path.unlink(missing_ok=True)

        time.sleep(3)
        room_id = api(
            "POST",
            f"{base}/_matrix/client/v3/createRoom",
            admin_token,
            {
                "preset": "private_chat",
                "invite": [args.master_user_id, args.worker_user_id],
                "name": "duo-smoke",
            },
        )["room_id"]
        enc = urllib.parse.quote(room_id, safe="")
        api("POST", f"{base}/_matrix/client/v3/rooms/{enc}/join", args.master_token, {})
        api("POST", f"{base}/_matrix/client/v3/rooms/{enc}/join", args.worker_token, {})
        api("POST", f"{base}/_matrix/client/v3/rooms/{enc}/join", admin_token, {})

        if not wait_member(base, admin_token, room_id, args.master_user_id, 20):
            raise SystemExit("FAIL: master did not join")
        if not wait_member(base, admin_token, room_id, args.worker_user_id, 20):
            raise SystemExit("FAIL: worker did not join")

        time.sleep(4)
        txn = str(int(time.time() * 1000))
        api(
            "PUT",
            f"{base}/_matrix/client/v3/rooms/{enc}/send/m.room.message/{txn}",
            admin_token,
            {"msgtype": "m.text", "body": "!discuss duo smoke test"},
        )

        deadline = time.time() + args.timeout
        bot_senders = {args.master_user_id, args.worker_user_id}
        saw_stop = False
        bot_msgs = 0
        last_count = -1
        stable = 0

        while time.time() < deadline:
            events = fetch_messages(base, admin_token, room_id)
            bot_msgs = sum(
                1
                for e in events
                if e.get("type") == "m.room.message"
                and e.get("sender") in bot_senders
                and e.get("content", {}).get("msgtype") == "m.text"
            )
            bodies = [
                e.get("content", {}).get("body", "")
                for e in events
                if e.get("sender") in bot_senders
                and e.get("type") == "m.room.message"
            ]
            if any(args.stop_marker in b for b in bodies):
                saw_stop = True
            if bot_msgs == last_count:
                stable += 1
            else:
                stable = 0
            last_count = bot_msgs
            if saw_stop and stable >= 2:
                break
            time.sleep(1.5)

        if bot_msgs < 2:
            raise SystemExit(f"FAIL: expected bot traffic, got {bot_msgs} messages")
        if bot_msgs > args.max_turns * 3:
            raise SystemExit(f"FAIL: runaway messages ({bot_msgs})")
        if not saw_stop:
            raise SystemExit(f"FAIL: stop marker {args.stop_marker} not seen")

        print(f"OK: duo conversation stopped ({bot_msgs} bot text messages, marker seen)")
    finally:
        master_proc.terminate()
        worker_proc.terminate()
        for proc in (master_proc, worker_proc):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
