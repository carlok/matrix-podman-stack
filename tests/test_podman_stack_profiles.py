"""podman-compose profile flag translation (no containers)."""

from __future__ import annotations

from tests.integration import podman_stack


def test_profile_args_split_and_trim(monkeypatch):
    monkeypatch.setattr(podman_stack, "_podman_compose_supports_profile", lambda: True)
    assert podman_stack.profile_args(" bus, llm ") == ["--profile", "bus", "--profile", "llm"]


def test_profile_args_skipped_without_flag_support(monkeypatch):
    monkeypatch.setattr(podman_stack, "_podman_compose_supports_profile", lambda: False)
    assert podman_stack.profile_args("bus") == []


def test_profile_args_empty(monkeypatch):
    monkeypatch.setattr(podman_stack, "_podman_compose_supports_profile", lambda: True)
    assert podman_stack.profile_args(None) == []
    assert podman_stack.profile_args("  ,  ") == []


def test_compose_cmd_places_profile_before_subcommand(monkeypatch):
    monkeypatch.setattr(podman_stack, "_podman_compose_supports_profile", lambda: True)
    cmd = podman_stack.compose_cmd("up", "-d", "nats", profiles="bus")
    assert cmd[0] == "podman-compose"
    assert cmd[-3:] == ["up", "-d", "nats"]
    assert cmd.index("--profile") < cmd.index("up")
    assert cmd[cmd.index("--profile") + 1] == "bus"
