from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from load_bot_config import env_key, load_config


def test_explicit_bot_list(tmp_path: Path):
    cfg = tmp_path / "bots.yaml"
    cfg.write_text(
        """
bots:
  - localpart: coordinator
    display_name: Coordinator
  - localpart: worker1
    display_name_template: "W {index}"
"""
    )
    bots = load_config(cfg)
    assert len(bots) == 2
    assert bots[0]["localpart"] == "coordinator"
    assert bots[1]["display_name"] == "worker1"


def test_pattern_generation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BOT_COUNT", raising=False)
    monkeypatch.delenv("BOT_NAME_PREFIX", raising=False)
    cfg = tmp_path / "bots.yaml"
    cfg.write_text(
        """
pattern:
  prefix: agent
  count: 3
  display_name_template: "Agent {index}"
"""
    )
    bots = load_config(cfg)
    assert [b["localpart"] for b in bots] == ["agent1", "agent2", "agent3"]
    assert bots[2]["display_name"] == "Agent 3"


def test_env_overrides_count_and_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BOT_COUNT", raising=False)
    monkeypatch.delenv("BOT_NAME_PREFIX", raising=False)
    cfg = tmp_path / "bots.yaml"
    cfg.write_text("pattern:\n  prefix: bot\n  count: 99\n")
    monkeypatch.setenv("BOT_COUNT", "2")
    monkeypatch.setenv("BOT_NAME_PREFIX", "svc")
    bots = load_config(cfg)
    assert [b["localpart"] for b in bots] == ["svc1", "svc2"]


def test_invalid_localpart_raises(tmp_path: Path):
    cfg = tmp_path / "bots.yaml"
    cfg.write_text('bots:\n  - localpart: "BAD SPACE"\n')
    with pytest.raises(ValueError, match="Invalid localpart"):
        load_config(cfg)


def test_count_must_be_positive(tmp_path: Path):
    cfg = tmp_path / "bots.yaml"
    cfg.write_text("pattern:\n  prefix: bot\n  count: 0\n")
    with pytest.raises(ValueError, match="count"):
        load_config(cfg)


def test_env_key():
    assert env_key("bot-1") == "BOT_BOT_1"


def test_cli_json_output(tmp_path: Path):
    cfg = tmp_path / "bots.yaml"
    cfg.write_text("pattern:\n  prefix: b\n  count: 1\n")
    env = {k: v for k, v in os.environ.items() if k not in ("BOT_COUNT", "BOT_NAME_PREFIX")}
    out = subprocess.check_output(
        [sys.executable, "scripts/load_bot_config.py", "--config", str(cfg), "--json"],
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    data = json.loads(out)
    assert data[0]["localpart"] == "b1"


def test_empty_prefix_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BOT_NAME_PREFIX", raising=False)
    cfg = tmp_path / "bots.yaml"
    cfg.write_text("pattern:\n  prefix: ''\n  count: 1\n")
    with pytest.raises(ValueError, match="prefix"):
        load_config(cfg)


def test_main_prints_lines(tmp_path: Path):
    cfg = tmp_path / "bots.yaml"
    cfg.write_text("pattern:\n  prefix: z\n  count: 1\n")
    env = {k: v for k, v in os.environ.items() if k not in ("BOT_COUNT", "BOT_NAME_PREFIX")}
    out = subprocess.check_output(
        [sys.executable, "scripts/load_bot_config.py", "--config", str(cfg)],
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    assert "z1\t" in out


def test_main_uses_bot_config_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = tmp_path / "custom.yaml"
    cfg.write_text("pattern:\n  prefix: envbot\n  count: 1\n")
    env = {k: v for k, v in os.environ.items() if k not in ("BOT_COUNT", "BOT_NAME_PREFIX")}
    env["BOT_CONFIG"] = str(cfg)
    out = subprocess.check_output(
        [sys.executable, "scripts/load_bot_config.py", "--json"],
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )
    assert json.loads(out)[0]["localpart"] == "envbot1"


def test_cli_missing_config_exits(tmp_path: Path):
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/load_bot_config.py",
            "--config",
            str(tmp_path / "missing.yaml"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
