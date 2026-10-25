#!/usr/bin/env python3
"""Small Synapse admin API helpers (rate limits, login)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request


def login(base_url: str, user: str, password: str) -> str:
    payload = json.dumps(
        {
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": user},
            "password": password,
        }
    ).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/_matrix/client/v3/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["access_token"]


def reset_password(base_url: str, admin_token: str, user_id: str, new_password: str) -> None:
    encoded = urllib.parse.quote(user_id, safe="")
    payload = json.dumps({"new_password": new_password, "logout_devices": False}).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/_synapse/admin/v1/reset_password/{encoded}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):
        return


def set_rate_limit_override(
    base_url: str, admin_token: str, user_id: str, messages_per_second: int, burst_count: int
) -> None:
    encoded = urllib.parse.quote(user_id, safe="")
    payload = json.dumps(
        {"messages_per_second": int(messages_per_second), "burst_count": int(burst_count)}
    ).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/_synapse/admin/v1/users/{encoded}/override_ratelimit",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {admin_token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30):
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    login_p = sub.add_parser("login")
    login_p.add_argument("--url", required=True)
    login_p.add_argument("--user", required=True)
    login_p.add_argument("--password", required=True)

    rl_p = sub.add_parser("rate-limit-override")
    rl_p.add_argument("--url", required=True)
    rl_p.add_argument("--admin-token", required=True)
    rl_p.add_argument("--user-id", required=True)
    rl_p.add_argument("--mps", type=int, default=1000)
    rl_p.add_argument("--burst", type=int, default=1000)

    rp_p = sub.add_parser("reset-password")
    rp_p.add_argument("--url", required=True)
    rp_p.add_argument("--admin-token", required=True)
    rp_p.add_argument("--user-id", required=True)
    rp_p.add_argument("--password", required=True)

    args = parser.parse_args()
    if args.cmd == "login":
        print(login(args.url, args.user, args.password))
    elif args.cmd == "rate-limit-override":
        set_rate_limit_override(args.url, args.admin_token, args.user_id, args.mps, args.burst)
    elif args.cmd == "reset-password":
        reset_password(args.url, args.admin_token, args.user_id, args.password)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(body, file=sys.stderr)
        raise SystemExit(exc.code) from exc
