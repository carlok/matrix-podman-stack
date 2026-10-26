from __future__ import annotations

from pathlib import Path

from duo import DuoConversation, DuoSettings


def _worker(tmp_path: Path, **kwargs) -> tuple[DuoConversation, str]:
    master = "@bot1:example.com"
    settings = DuoSettings(
        enabled=True,
        role="worker",
        peer_mxids={master},
        max_turns=kwargs.get("max_turns", 6),
        stop_marker="[DONE]",
        cooldown_seconds=0.0,
        command_prefix="!discuss",
        state_dir=tmp_path,
    )
    return DuoConversation(settings, "@bot2:example.com"), master


def test_worker_requires_mention(tmp_path: Path):
    conv, master = _worker(tmp_path)
    marker = "[duo thread=t turn=1 max=6]"
    reply = conv.process("!r:ex", "e1", master, f"{marker} hi", mentioned=False, is_bot_sender=True)
    assert reply is None


def test_thread_id_mismatch_ignored(tmp_path: Path):
    conv, master = _worker(tmp_path)
    conv.process("!r:ex", "e0", master, "[duo thread=aaa turn=1 max=6] start", True, True)
    reply = conv.process(
        "!r:ex",
        "e1",
        master,
        "[duo thread=bbb turn=2 max=6] wrong thread",
        True,
        True,
    )
    assert reply is None


def test_master_follow_up_when_mentioned(tmp_path: Path):
    settings = DuoSettings(
        enabled=True,
        role="master",
        peer_mxids={"@bot2:example.com"},
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0.0,
        command_prefix="!discuss",
        state_dir=tmp_path,
    )
    conv = DuoConversation(settings, "@bot1:example.com")
    conv.process("!r:ex", "e0", "@admin:ex", "!discuss topic", False, False)
    state = conv.load("!r:ex")
    marker = conv.format_marker(state.thread_id, 1)
    worker = "@bot2:example.com"
    reply = conv.process(
        "!r:ex",
        "e1",
        worker,
        f"{marker} @bot1:example.com continue",
        True,
        True,
    )
    assert reply is not None
    assert "master follow-up" in reply.body


def test_master_ignores_unmentioned_bot_without_marker(tmp_path: Path):
    settings = DuoSettings(
        enabled=True,
        role="master",
        peer_mxids={"@bot2:example.com"},
        max_turns=6,
        stop_marker="[DONE]",
        cooldown_seconds=0.0,
        command_prefix="!discuss",
        state_dir=tmp_path,
    )
    conv = DuoConversation(settings, "@bot1:example.com")
    conv.process("!r:ex", "e0", "@admin:ex", "!discuss topic", False, False)
    reply = conv.process("!r:ex", "e1", "@bot2:example.com", "noise", False, True)
    assert reply is None
