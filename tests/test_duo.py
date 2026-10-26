from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from duo import DuoConversation, DuoSettings, RoomDuoState


@pytest.fixture
def tmp_state(tmp_path: Path) -> Path:
    return tmp_path / "duo-state"


def make_settings(
    tmp_state: Path,
    *,
    role: str = "master",
    max_turns: int = 6,
    peers: set[str] | None = None,
    cooldown: float = 0.0,
) -> DuoSettings:
    return DuoSettings(
        enabled=True,
        role=role,
        peer_mxids=peers or {"@bot2:example.com"},
        max_turns=max_turns,
        stop_marker="[DONE]",
        cooldown_seconds=cooldown,
        command_prefix="!discuss",
        state_dir=tmp_state,
    )


def test_parse_and_strip_markers():
    body = "[duo thread=abc123 turn=2 max=6] hello"
    assert DuoConversation.parse_marker(body) == ("abc123", 2, 6)
    assert DuoConversation.strip_markers(body) == "hello"
    assert DuoConversation.parse_marker("no marker") is None


def test_format_marker():
    s = DuoSettings(
        enabled=True,
        role="master",
        peer_mxids=set(),
        max_turns=4,
        stop_marker="[DONE]",
        cooldown_seconds=0,
        command_prefix="!discuss",
        state_dir=Path("/tmp"),
    )
    conv = DuoConversation(s, "@bot1:example.com")
    assert conv.format_marker("tid", 3) == "[duo thread=tid turn=3 max=4]"


def test_dedupe_events():
    state = RoomDuoState()
    assert state.mark_seen("e1") is True
    assert state.mark_seen("e1") is False


def test_persistence_roundtrip(tmp_state: Path):
    conv = DuoConversation(make_settings(tmp_state), "@bot1:example.com")
    room = "!room:example.com"
    state = RoomDuoState(thread_id="t1", turn=2, active=True, last_reply_at=1.5)
    state.mark_seen("ev1")
    conv.save(room, state)
    loaded = conv.load(room)
    assert loaded.thread_id == "t1"
    assert loaded.turn == 2
    assert loaded.active is True
    assert "ev1" in loaded.seen_event_ids
    path = conv._path(room)
    assert path.is_file()
    assert json.loads(path.read_text())["turn"] == 2


def test_master_starts_discuss(tmp_state: Path):
    conv = DuoConversation(make_settings(tmp_state, role="master"), "@bot1:example.com")
    reply = conv.process(
        "!r:ex",
        "e1",
        "@admin:ex",
        "!discuss quantum",
        mentioned=False,
        is_bot_sender=False,
    )
    assert reply is not None
    assert "topic: quantum" in reply.body
    assert "[duo thread=" in reply.body


def test_human_resets_active_thread(tmp_state: Path):
    conv = DuoConversation(make_settings(tmp_state, role="master"), "@bot1:example.com")
    conv.process("!r:ex", "e1", "@admin:ex", "!discuss x", False, False)
    state = conv.load("!r:ex")
    assert state.active is True
    conv.process("!r:ex", "e2", "@admin:ex", "hello human", False, False)
    state = conv.load("!r:ex")
    assert state.active is False
    assert state.turn == 0


def test_stop_marker_ends_conversation(tmp_state: Path):
    master = "@bot1:example.com"
    conv = DuoConversation(
        make_settings(tmp_state, role="worker", peers={master}),
        "@bot2:example.com",
    )
    marker = "[duo thread=abc turn=1 max=6]"
    conv.process("!r:ex", "e1", master, f"{marker} start", True, True)
    reply = conv.process("!r:ex", "e2", master, f"{marker} please stop [DONE]", True, True)
    assert reply is not None
    assert "Conversation stopped" in reply.body
    assert conv.load("!r:ex").active is False


def test_worker_turn_cap_without_done_in_input(tmp_state: Path):
    """BOT_MAX_TURNS: worker stops when marker turn >= max, no [DONE] in incoming body."""
    max_turns = 3
    master = "@bot1:example.com"
    conv = DuoConversation(
        make_settings(tmp_state, role="worker", max_turns=max_turns, peers={master}),
        "@bot2:example.com",
    )
    tid = "threadcap01"
    marker_at_cap = f"[duo thread={tid} turn={max_turns} max={max_turns}]"
    conv.process(
        "!r:ex",
        "e0",
        master,
        f"[duo thread={tid} turn=1 max={max_turns}] seed",
        True,
        True,
    )
    reply = conv.process(
        "!r:ex",
        "e1",
        master,
        f"{marker_at_cap} worker should stop on cap",
        True,
        True,
    )
    assert reply is not None
    assert "turn cap" in reply.body
    assert "[DONE]" not in f"{marker_at_cap} worker should stop on cap"
    assert conv.load("!r:ex").active is False


def test_master_turn_cap_notice(tmp_state: Path):
    conv = DuoConversation(
        make_settings(tmp_state, role="master", max_turns=2),
        "@bot1:example.com",
    )
    worker = "@bot2:example.com"
    conv.process("!r:ex", "e0", "@admin:ex", "!discuss go", False, False)
    state = conv.load("!r:ex")
    marker = conv.format_marker(state.thread_id, 2)
    conv.process("!r:ex", "e1", worker, f"{marker} ping @bot1:example.com", True, True)
    reply = conv.process(
        "!r:ex",
        "e2",
        worker,
        f"{marker} again @bot1:example.com",
        True,
        True,
    )
    assert reply is not None
    assert "Turn cap 2" in reply.body


def test_cooldown_blocks_bot_reply(tmp_state: Path):
    master = "@bot1:example.com"
    conv = DuoConversation(
        make_settings(tmp_state, role="worker", max_turns=10, cooldown=60.0, peers={master}),
        "@bot2:example.com",
    )
    state = conv.load("!r:ex")
    state.active = True
    state.thread_id = "t"
    state.turn = 1
    state.last_reply_at = time.time()
    conv.save("!r:ex", state)
    marker = "[duo thread=t turn=1 max=10]"
    reply = conv.process("!r:ex", "e1", master, f"{marker} hi", True, True)
    assert reply is None


def test_peer_allowlist(tmp_state: Path):
    conv = DuoConversation(
        make_settings(tmp_state, role="worker", peers={"@bot1:example.com"}),
        "@bot2:example.com",
    )
    reply = conv.process(
        "!r:ex",
        "e1",
        "@stranger:example.com",
        "[duo thread=x turn=1 max=6] hi",
        True,
        True,
    )
    assert reply is None


def test_env_int_invalid_max_turns(monkeypatch: pytest.MonkeyPatch, tmp_state: Path):
    monkeypatch.setenv("BOT_MAX_TURNS", "not-a-number")
    s = DuoSettings.from_env()
    assert s.max_turns == 6


def test_seen_event_ids_trim(tmp_state: Path):
    state = RoomDuoState()
    for i in range(205):
        state.mark_seen(f"e{i}")
    assert len(state.seen_event_ids) == 200


def test_duo_settings_from_env(monkeypatch: pytest.MonkeyPatch, tmp_state: Path):
    monkeypatch.setenv("BOT_DUO_ENABLED", "true")
    monkeypatch.setenv("BOT_DUO_ROLE", "worker")
    monkeypatch.setenv("BOT_DUO_PEER_MXIDS", "@a:ex,@b:ex")
    monkeypatch.setenv("BOT_MAX_TURNS", "9")
    monkeypatch.setenv("BOT_DUO_STATE_DIR", str(tmp_state))
    s = DuoSettings.from_env()
    assert s.enabled is True
    assert s.role == "worker"
    assert s.peer_mxids == {"@a:ex", "@b:ex"}
    assert s.max_turns == 9


def test_load_corrupt_state(tmp_state: Path):
    conv = DuoConversation(make_settings(tmp_state), "@bot1:example.com")
    path = conv._path("!r:ex")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert conv.load("!r:ex").turn == 0


def test_process_disabled_returns_none(tmp_state: Path):
    s = make_settings(tmp_state)
    s.enabled = False
    conv = DuoConversation(s, "@bot1:example.com")
    assert conv.process("!r", "e", "@a:ex", "!discuss x", False, False) is None
