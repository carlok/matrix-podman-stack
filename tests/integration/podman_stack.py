"""Shared helpers for Podman Compose integration tests."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GARAGE241_OVERRIDE = ROOT / "tests" / "integration" / "compose.garage241.override.yaml"

PG16_ENV = {
    "POSTGRES_SYNAPSE_IMAGE": "docker.io/library/postgres:16.15-bookworm",
    "POSTGRES_SYNAPSE_MOUNT": "/var/lib/postgresql/data",
    "POSTGRES_TELEGRAM_IMAGE": "docker.io/library/postgres:16.15-bookworm",
    "POSTGRES_TELEGRAM_MOUNT": "/var/lib/postgresql/data",
}

PG18_ENV = {
    "POSTGRES_SYNAPSE_IMAGE": "docker.io/library/postgres:18.6-bookworm",
    "POSTGRES_SYNAPSE_MOUNT": "/var/lib/postgresql",
    "POSTGRES_TELEGRAM_IMAGE": "docker.io/library/postgres:18.6-bookworm",
    "POSTGRES_TELEGRAM_MOUNT": "/var/lib/postgresql",
}


class ComposeError(RuntimeError):
    def __init__(self, message: str, *, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


_POSTGRES_ENV_KEYS = (
    "POSTGRES_SYNAPSE_IMAGE",
    "POSTGRES_SYNAPSE_MOUNT",
    "POSTGRES_TELEGRAM_IMAGE",
    "POSTGRES_TELEGRAM_MOUNT",
)


def _merge_env(extra: dict[str, str] | None) -> dict[str, str]:
    merged = os.environ.copy()
    merged.setdefault("HOST_UID", str(os.getuid()))
    merged.setdefault("HOST_GID", str(os.getgid()))
    for key in _POSTGRES_ENV_KEYS:
        merged.pop(key, None)
    if extra:
        merged.update(extra)
    return merged


def run(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged = _merge_env(env)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise ComposeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}",
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    return proc


def compose_cmd(*args: str, extra_files: list[Path] | None = None) -> list[str]:
    # ubuntu-latest defaults `podman compose` to the docker-compose plugin; use podman-compose in CI.
    cmd = ["podman-compose", "-f", str(ROOT / "compose.yaml")]
    for path in extra_files or []:
        cmd.extend(["-f", str(path)])
    cmd.extend(args)
    return cmd


def compose(
    *args: str,
    profiles: str | None = None,
    extra_files: list[Path] | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    cmd = compose_cmd(*args, extra_files=extra_files)
    merged: dict[str, str] = {}
    if profiles:
        merged["COMPOSE_PROFILES"] = profiles
    if env:
        merged.update(env)
    return run(cmd, env=merged, timeout=timeout)


def purge_compose_project() -> None:
    """Remove leftover containers/networks (podman-compose down can miss deps on CI)."""
    run(
        [
            "podman",
            "rm",
            "-af",
            "--filter",
            "label=io.podman.compose.project=matrix-podman-stack",
        ],
        check=False,
        timeout=300,
    )
    run(["podman", "network", "rm", "matrix-podman-stack_matrix-db"], check=False, timeout=60)


def compose_down(profiles: str | None = None, extra_files: list[Path] | None = None) -> None:
    run(
        compose_cmd("down", "-v", extra_files=extra_files),
        env={"COMPOSE_PROFILES": profiles} if profiles else None,
        check=False,
        timeout=900,
    )
    purge_compose_project()


def bootstrap_synapse(*, env: dict[str, str] | None = None) -> None:
    """Generate homeserver.yaml; postgres-synapse must already be up and healthy."""
    compose(
        "run",
        "--rm",
        "--no-deps",
        "synapse-bootstrap",
        profiles="bootstrap",
        env=env,
        timeout=600,
    )


def wait_until(predicate, *, timeout_s: float = 120.0, interval_s: float = 2.0, description: str = "") -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval_s)
    label = description or "condition"
    raise TimeoutError(f"Timed out waiting for {label}")


def wait_http(
    url: str,
    *,
    timeout_s: float = 120.0,
    interval_s: float = 2.0,
    headers: dict[str, str] | None = None,
) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status < 400:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
        time.sleep(interval_s)
    raise TimeoutError(f"Timed out waiting for {url}: {last_err}")


def wait_healthz(port: int, path: str = "/health") -> None:
    wait_http(f"http://127.0.0.1:{port}{path}")


def wait_pg_isready(
    service: str,
    user: str,
    *,
    env: dict[str, str] | None = None,
    profiles: str | None = None,
    timeout_s: float = 120.0,
) -> None:
    def ready() -> bool:
        proc = compose(
            "exec",
            "-T",
            service,
            "pg_isready",
            "-U",
            user,
            env=env,
            profiles=profiles,
            timeout=30,
        )
        return proc.returncode == 0

    wait_until(ready, timeout_s=timeout_s, description=f"{service} pg_isready")


def dump_compose_logs(services: list[str] | None = None) -> str:
    args = ["logs", "--tail", "200"]
    if services:
        args.extend(services)
    try:
        proc = compose(*args, timeout=120)
        return proc.stdout + proc.stderr
    except ComposeError as exc:
        return exc.stdout + exc.stderr


def apply_compose_postgres_env(overrides: dict[str, str] | None) -> None:
    """Patch .env so podman-compose sees Postgres image/mount overrides."""
    path = ROOT / ".env"
    lines = path.read_text().splitlines()
    keys = set(_POSTGRES_ENV_KEYS)
    kept = [ln for ln in lines if not any(ln.startswith(f"{k}=") for k in keys)]
    if overrides:
        for key in _POSTGRES_ENV_KEYS:
            if key in overrides:
                kept.append(f"{key}={overrides[key]}")
    path.write_text("\n".join(kept) + "\n")


def write_integration_env(data_dir: Path, *, server_name: str = "ci.integration.test") -> None:
    """Materialize .env for an isolated DATA_DIR (non-secret test values)."""
    example = (ROOT / ".env.example").read_text()
    uid = os.getuid()
    gid = os.getgid()
    hex32 = secrets.token_hex(32)
    rpc = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    replacements = {
        "DATA_DIR=./data": f"DATA_DIR={data_dir}",
        "SYNAPSE_SERVER_NAME=matrix.example.com": f"SYNAPSE_SERVER_NAME={server_name}",
        "PUBLIC_HOMESERVER_URL=https://matrix.example.com": "PUBLIC_HOMESERVER_URL=http://127.0.0.1:8008",
        "PUBLIC_ELEMENT_URL=https://chat.example.com": "PUBLIC_ELEMENT_URL=http://127.0.0.1:8080",
        "change_me_synapse_db": hex32,
        "change_me_registration_shared_secret": secrets.token_hex(32),
        "change_me_macaroon_secret": secrets.token_hex(32),
        "change_me_form_secret": secrets.token_hex(32),
        "change_me_telegram_db": secrets.token_hex(32),
        "change_me_nats": hex32,
        "change_me_valkey": hex32,
        "change_me_garage_admin": hex32,
        "change_me_grafana": hex32,
        "change_me_qdrant": hex32,
        "TELEGRAM_API_ID=": "TELEGRAM_API_ID=12345",
        "TELEGRAM_API_HASH=": "TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef",
    }
    text = example
    for old, new in replacements.items():
        text = text.replace(old, new)
    text += f"\nHOST_UID={uid}\nHOST_GID={gid}\n"
    (ROOT / ".env").write_text(text)


def prepare_data_dirs(data_dir: Path) -> None:
    uid = os.getuid()
    gid = os.getgid()
    subdirs = [
        "postgres-synapse",
        "postgres-telegram",
        "synapse",
        "synapse/media_store",
        "synapse/uploads",
        "element",
        "mautrix-telegram",
        "prometheus",
        "grafana",
        "bots",
        "nats/jetstream",
        "valkey",
        "garage/meta",
        "garage/data",
        "qdrant/storage",
        "ollama",
    ]
    for rel in subdirs:
        path = data_dir / rel
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(path, uid, gid)
        except OSError:
            pass
    run(
        [
            "python3",
            str(ROOT / "scripts" / "render_element_config.py"),
            "--homeserver-url",
            "http://127.0.0.1:8008",
            "--server-name",
            "ci.integration.test",
            "--output",
            str(data_dir / "element" / "config.json"),
        ]
    )


def register_user(password: str, user: str = "migrateuser", admin: bool = False) -> None:
    admin_args = ["-a"] if admin else ["--no-admin"]
    compose(
        "exec",
        "-T",
        "synapse",
        "register_new_matrix_user",
        "-c",
        "/data/homeserver.yaml",
        "-u",
        user,
        "-p",
        password,
        *admin_args,
        "http://localhost:8008",
        timeout=120,
    )


def matrix_login(base: str, user: str, password: str) -> str:
    from matrix_testutil import login

    return login(base, user, password)


def prometheus_target_up(job: str = "synapse") -> bool:
    with urllib.request.urlopen("http://127.0.0.1:9090/api/v1/targets", timeout=30) as resp:
        data = json.loads(resp.read().decode())
    for target in data.get("data", {}).get("activeTargets", []):
        if target.get("labels", {}).get("job") == job:
            return target.get("health") == "up"
    return False


def grafana_prometheus_query(admin_password: str) -> bool:
    auth = f"admin:{admin_password}".encode()
    import base64

    headers = {"Authorization": f"Basic {base64.b64encode(auth).decode()}"}
    ds_req = urllib.request.Request(
        "http://127.0.0.1:3000/api/datasources",
        headers=headers,
    )
    with urllib.request.urlopen(ds_req, timeout=30) as resp:
        datasources = json.loads(resp.read().decode())
    prom = next((d for d in datasources if d.get("type") == "prometheus"), None)
    if prom is None:
        prom_body = json.dumps(
            {
                "name": "Prometheus",
                "type": "prometheus",
                "url": "http://prometheus:9090",
                "access": "proxy",
                "isDefault": True,
            }
        ).encode()
        create = urllib.request.Request(
            "http://127.0.0.1:3000/api/datasources",
            data=prom_body,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(create, timeout=30):
            pass
    prom_id = prom["id"] if prom else None
    if prom_id is None:
        with urllib.request.urlopen(ds_req, timeout=30) as resp:
            datasources = json.loads(resp.read().decode())
        prom_id = next((d["id"] for d in datasources if d.get("type") == "prometheus"), None)
    assert prom_id is not None
    enc_query = urllib.parse.quote('up{job="synapse"}', safe="")
    proxy_url = f"http://127.0.0.1:3000/api/datasources/proxy/{prom_id}/api/v1/query?query={enc_query}"
    q = urllib.request.Request(proxy_url, headers=headers)
    with urllib.request.urlopen(q, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    results = payload.get("data", {}).get("result", [])
    return payload.get("status") == "success" and bool(results)


def rm_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def read_pg_version(volume_host: Path, *, relative_dir: str = "") -> str:
    rel = f"{relative_dir.rstrip('/')}/PG_VERSION" if relative_dir else "PG_VERSION"
    proc = run(
        [
            "podman",
            "run",
            "--rm",
            "-v",
            f"{volume_host}:/v:ro,Z",
            "docker.io/library/busybox:1.36.1",
            "cat",
            f"/v/{rel}",
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise FileNotFoundError(f"PG_VERSION not readable at {volume_host}/{rel}")
    return proc.stdout.strip()


def env_value(key: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise KeyError(key)
