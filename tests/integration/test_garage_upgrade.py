"""Garage v2.4.1 → v2.5.0 in-place data directory upgrade."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from . import podman_stack

pytestmark = pytest.mark.integration

GARAGE_COMPOSE_ENV = {
    "COMPOSE_FILE": f"{podman_stack.ROOT / 'compose.yaml'}:{podman_stack.GARAGE241_OVERRIDE}",
}


def _garage_key_credentials() -> tuple[str, str]:
    proc = podman_stack.compose(
        "exec",
        "-T",
        "garage",
        "/garage",
        "key",
        "create",
        "upgrade-test-key",
        profiles="object",
        env=GARAGE_COMPOSE_ENV,
    )
    key_id = ""
    secret = ""
    for line in (proc.stdout + proc.stderr).splitlines():
        if "Key ID:" in line:
            key_id = line.split(":", 1)[1].strip()
        if "Secret key:" in line:
            secret = line.split(":", 1)[1].strip()
    assert key_id and secret
    return key_id, secret


def _s3_cp_string(key_id: str, secret: str, marker: str, direction: str) -> str:
    if direction == "put":
        cmd = (
            f"echo -n '{marker}' | podman run --rm --network=host "
            f"-e AWS_ACCESS_KEY_ID={key_id} -e AWS_SECRET_ACCESS_KEY={secret} "
            "docker.io/amazon/aws-cli:2.22.35 s3 --endpoint-url http://127.0.0.1:13900 "
            "cp - s3://bot-artifacts/upgrade-marker.txt --region garage"
        )
        subprocess.run(cmd, shell=True, check=True, timeout=120)
        return marker
    cmd = (
        f"podman run --rm --network=host "
        f"-e AWS_ACCESS_KEY_ID={key_id} -e AWS_SECRET_ACCESS_KEY={secret} "
        "docker.io/amazon/aws-cli:2.22.35 s3 --endpoint-url http://127.0.0.1:13900 "
        "cp s3://bot-artifacts/upgrade-marker.txt - --region garage"
    )
    out = subprocess.run(cmd, shell=True, check=True, capture_output=True, timeout=120)
    return out.stdout.decode()


@pytest.mark.timeout(900)
def test_garage_in_place_upgrade_241_to_250(integration_data_dir: Path):
    marker = "garage-upgrade-marker"
    try:
        podman_stack.run(["./scripts/bootstrap-object.sh"], env=GARAGE_COMPOSE_ENV, timeout=600)
        key_id, secret = _garage_key_credentials()
        _s3_cp_string(key_id, secret, marker, "put")
        assert _s3_cp_string(key_id, secret, marker, "get") == marker

        podman_stack.compose(
            "stop",
            "garage",
            profiles="object",
            env=GARAGE_COMPOSE_ENV,
        )
        podman_stack.compose("up", "-d", "garage", profiles="object")
        podman_stack.wait_http("http://127.0.0.1:13903/health", timeout_s=120)
        assert _s3_cp_string(key_id, secret, marker, "get") == marker
    except Exception:
        print(podman_stack.dump_compose_logs(["garage"]))
        raise
    finally:
        podman_stack.compose_down(profiles="object")
