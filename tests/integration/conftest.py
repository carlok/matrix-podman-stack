"""Fixtures for Podman integration tests."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from . import podman_stack

ROOT = podman_stack.ROOT


@pytest.fixture(scope="session")
def podman_available() -> None:
    proc = podman_stack.run(["podman", "info"], check=False, timeout=60)
    if proc.returncode != 0:
        pytest.skip("Podman not available")


@pytest.fixture
def integration_data_dir(podman_available, tmp_path_factory) -> Path:
    data_dir = tmp_path_factory.mktemp("matrix-data")
    podman_stack.write_integration_env(data_dir)
    podman_stack.prepare_data_dirs(data_dir)
    yield data_dir
    podman_stack.compose_down()
    podman_stack.purge_compose_project()
    if os.environ.get("INTEGRATION_KEEP_DATA"):
        return
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _chdir_root():
    prev = os.getcwd()
    os.chdir(ROOT)
    try:
        yield
    finally:
        os.chdir(prev)
