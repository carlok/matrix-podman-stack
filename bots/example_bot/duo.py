"""Opt-in master/worker bot-to-bot conversations with anti-loop guards."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("example-bot.duo")

MARKER_RE = re.compile(
    r"\[duo thread=([^\s\]]+) turn=(\d+) max=(\d+)\]",
    re.IGNORECASE,
)


@dataclass
class DuoReply:
    body: str
    msgtype: str = "m.text"


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name, str(default)).lower()
    return val in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass
class DuoSettings:
    enabled: bool
    role: str
    peer_mxids: set[str]
    max_turns: int
    stop_marker: str
    cooldown_seconds: float
    command_prefix: str
    state_dir: Path

    @classmethod
    def from_env(cls) -> DuoSettings:
        peers = {
            s.strip()
            for s in os.environ.get("BOT_DUO_PEER_MXIDS", "").split(",")
            if s.strip()
        }
        return cls(
            enabled=_env_bool("BOT_DUO_ENABLED"),
            role=os.environ.get("BOT_DUO_ROLE", "").strip().lower(),
            peer_mxids=peers,
            max_turns=_env_int("BOT_MAX_TURNS", 6),
            stop_marker=os.environ.get("BOT_DUO_STOP_MARKER", "[DONE]"),
            cooldown_seconds=float(os.environ.get("BOT_DUO_COOLDOWN_SECONDS", "2")),
            command_prefix=os.environ.get("BOT_DUO_COMMAND_PREFIX", "!discuss").strip(),
            state_dir=Path(os.environ.get("BOT_DUO_STATE_DIR", "./data/bots/duo-state")),
        )


@dataclass
class RoomDuoState:
    thread_id: str = ""
    turn: int = 0
    active: bool = False
    seen_event_ids: list[str] = field(default_factory=list)
    last_reply_at: float = 0.0

    def mark_seen(self, event_id: str) -> bool:
        if event_id in self.seen_event_ids:
            return False
        self.seen_event_ids.append(event_id)
        if len(self.seen_event_ids) > 200:
            self.seen_event_ids = self.seen_event_ids[-200:]
        return True


class DuoConversation:
    def __init__(self, settings: DuoSettings, own_user_id: str) -> None:
        self.settings = settings
        self.own_user_id = own_user_id
        self.settings.state_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, room_id: str) -> Path:
        safe_room = room_id.replace(":", "_").replace("/", "_")
        safe_user = self.own_user_id.replace(":", "_").replace("/", "_")
        return self.settings.state_dir / f"{safe_user}__{safe_room}.json"

    def load(self, room_id: str) -> RoomDuoState:
        path = self._path(room_id)
        if not path.is_file():
            return RoomDuoState()
        try:
            raw = json.loads(path.read_text())
            return RoomDuoState(
                thread_id=raw.get("thread_id", ""),
                turn=int(raw.get("turn", 0)),
                active=bool(raw.get("active", False)),
                seen_event_ids=list(raw.get("seen_event_ids", [])),
                last_reply_at=float(raw.get("last_reply_at", 0.0)),
            )
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            log.warning("duo state load failed: %s", exc)
            return RoomDuoState()

    def save(self, room_id: str, state: RoomDuoState) -> None:
        path = self._path(room_id)
        path.write_text(
            json.dumps(
                {
                    "thread_id": state.thread_id,
                    "turn": state.turn,
                    "active": state.active,
                    "seen_event_ids": state.seen_event_ids[-200:],
                    "last_reply_at": state.last_reply_at,
                },
                indent=2,
            )
        )
        path.chmod(0o600)

    def format_marker(self, thread_id: str, turn: int) -> str:
        return f"[duo thread={thread_id} turn={turn} max={self.settings.max_turns}]"

    @staticmethod
    def parse_marker(body: str) -> tuple[str, int, int] | None:
        match = MARKER_RE.search(body)
        if not match:
            return None
        return match.group(1), int(match.group(2)), int(match.group(3))

    @staticmethod
    def strip_markers(body: str) -> str:
        return MARKER_RE.sub("", body).strip()

    def stop_in(self, body: str) -> bool:
        return self.settings.stop_marker in body

    def peer_ok(self, sender: str) -> bool:
        return not self.settings.peer_mxids or sender in self.settings.peer_mxids

    def cooldown_ok(self, state: RoomDuoState) -> bool:
        if self.settings.cooldown_seconds <= 0:
            return True
        return (time.time() - state.last_reply_at) >= self.settings.cooldown_seconds

    def process(
        self,
        room_id: str,
        event_id: str,
        sender: str,
        body: str,
        mentioned: bool,
        is_bot_sender: bool,
    ) -> DuoReply | None:
        if not self.settings.enabled:
            return None

        state = self.load(room_id)
        if not state.mark_seen(event_id):
            return None

        if not is_bot_sender:
            if state.active:
                state.active = False
                state.turn = 0
                state.thread_id = ""
                self.save(room_id, state)
                log.info("Human message ended duo thread in %s", room_id)
            if self.settings.role != "master":
                self.save(room_id, state)
                return None
            prefix = self.settings.command_prefix.lower()
            if not body.strip().lower().startswith(prefix):
                self.save(room_id, state)
                return None
            topic = body.strip()[len(self.settings.command_prefix) :].strip() or "(topic)"
            peer = next(iter(self.settings.peer_mxids), "")
            thread_id = uuid.uuid4().hex[:12]
            state.thread_id = thread_id
            state.turn = 1
            state.active = True
            self.save(room_id, state)
            marker = self.format_marker(thread_id, 1)
            return DuoReply(f"{marker} {peer} topic: {topic}")

        if not self.peer_ok(sender):
            self.save(room_id, state)
            return None

        parsed = self.parse_marker(body)
        if parsed:
            tid, turn, _ = parsed
            if state.thread_id and tid != state.thread_id:
                self.save(room_id, state)
                return None
            state.thread_id = tid
            state.turn = turn
            state.active = True

        if self.stop_in(body):
            state.active = False
            self.save(room_id, state)
            return DuoReply(
                f"Conversation stopped {self.settings.stop_marker}",
                msgtype="m.notice",
            )

        if is_bot_sender and not self.cooldown_ok(state):
            self.save(room_id, state)
            return None

        if self.settings.role == "worker":
            if not mentioned or not state.active:
                self.save(room_id, state)
                return None
            if parsed and parsed[1] >= self.settings.max_turns:
                state.active = False
                self.save(room_id, state)
                return DuoReply(
                    f"(worker stub) turn cap {self.settings.stop_marker}",
                    msgtype="m.text",
                )
            next_turn = max(state.turn, 1) + 1
            topic = self.strip_markers(body)
            done = next_turn >= self.settings.max_turns
            reply = f"(worker stub) {topic[:350]}"
            if done:
                reply = f"{reply} {self.settings.stop_marker}"
                state.active = False
            state.turn = next_turn
            state.last_reply_at = time.time()
            self.save(room_id, state)
            marker = self.format_marker(state.thread_id, next_turn)
            peer = next(iter(self.settings.peer_mxids), "")
            tail = f" {peer}" if peer and not done else ""
            return DuoReply(f"{marker}{tail} {reply}")

        if self.settings.role == "master" and state.active:
            if not mentioned and not parsed:
                self.save(room_id, state)
                return None
            next_turn = state.turn + 1
            if next_turn > self.settings.max_turns:
                state.active = False
                self.save(room_id, state)
                return DuoReply(
                    f"Turn cap {self.settings.max_turns} {self.settings.stop_marker}",
                    msgtype="m.notice",
                )
            peer = next(iter(self.settings.peer_mxids), "")
            prompt = self.strip_markers(body)
            state.turn = next_turn
            state.last_reply_at = time.time()
            self.save(room_id, state)
            marker = self.format_marker(state.thread_id, next_turn)
            return DuoReply(f"{marker} {peer} master follow-up: {prompt[:280]}")

        self.save(room_id, state)
        return None
