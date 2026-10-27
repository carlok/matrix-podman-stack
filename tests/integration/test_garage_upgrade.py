"""Garage v2.4.1 → v2.5.0 in-place data directory upgrade."""

from __future__ import annotations

from pathlib import Path

import boto3
import pytest
from botocore.config import Config

from . import podman_stack

pytestmark = pytest.mark.integration

GARAGE_COMPOSE_ENV = {
    "COMPOSE_FILE": f"{podman_stack.ROOT / 'compose.yaml'}:{podman_stack.GARAGE241_OVERRIDE}",
}

S3_ENDPOINT = "http://127.0.0.1:13900"
S3_BUCKET = "bot-artifacts"
S3_KEY = "upgrade-marker.txt"


def _s3_client(key_id: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name="garage",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


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


def _s3_put_get(key_id: str, secret: str, marker: str) -> None:
    client = _s3_client(key_id, secret)
    client.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=marker.encode())
    body = client.get_object(Bucket=S3_BUCKET, Key=S3_KEY)["Body"].read().decode()
    assert body == marker


@pytest.mark.timeout(900)
def test_garage_in_place_upgrade_241_to_250(integration_data_dir: Path):
    marker = "garage-upgrade-marker"
    try:
        podman_stack.run(["./scripts/bootstrap-object.sh"], env=GARAGE_COMPOSE_ENV, timeout=600)
        key_id, secret = _garage_key_credentials()
        _s3_put_get(key_id, secret, marker)

        podman_stack.compose(
            "stop",
            "garage",
            profiles="object",
            env=GARAGE_COMPOSE_ENV,
        )
        podman_stack.compose("up", "-d", "garage", profiles="object")
        podman_stack.wait_http("http://127.0.0.1:13903/health", timeout_s=180)
        _s3_put_get(key_id, secret, marker)
    except Exception:
        print(podman_stack.dump_compose_logs(["garage"]))
        raise
    finally:
        podman_stack.compose_down(profiles="object")
