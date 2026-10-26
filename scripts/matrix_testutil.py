"""Small Matrix Client-Server API helpers for integration smoke scripts."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request


def api(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def login(base: str, user: str, password: str) -> str:
    return api(
        "POST",
        f"{base}/_matrix/client/v3/login",
        body={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": user},
            "password": password,
        },
    )["access_token"]


def wait_member(base: str, token: str, room_id: str, user_id: str, timeout_s: float) -> bool:
    enc = urllib.parse.quote(room_id, safe="")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        state = api("GET", f"{base}/_matrix/client/v3/rooms/{enc}/joined_members", token)
        if user_id in state.get("joined", {}):
            return True
        time.sleep(0.5)
    return False


def fetch_messages(base: str, token: str, room_id: str, limit: int = 50) -> list[dict]:
    enc = urllib.parse.quote(room_id, safe="")
    data = api(
        "GET",
        f"{base}/_matrix/client/v3/rooms/{enc}/messages?dir=b&limit={limit}",
        token,
    )
    return data.get("chunk", [])
