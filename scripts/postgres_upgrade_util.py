"""Helpers for PostgreSQL 16 → 18 data-directory layout detection."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

PG18_DATA_SUBDIR = Path("18") / "docker"
UPGRADE_MARKER_NAME = ".postgres-upgraded-to-18"


class VolumeLayout(str, Enum):
    """Layout of a host directory bind-mounted for Postgres."""

    EMPTY = "empty"
    LEGACY_ROOT = "legacy_root"
    PG18 = "pg18"
    UPGRADED_MARKER = "upgraded_marker"
    UNKNOWN = "unknown"


def read_pg_major(pgdata_dir: Path) -> int | None:
    """Return major version from PG_VERSION, or None if missing/invalid."""
    version_file = pgdata_dir / "PG_VERSION"
    if not version_file.is_file():
        return None
    text = version_file.read_text(encoding="utf-8").strip()
    if not text.isdigit():
        return None
    return int(text)


def pg18_pgdata_dir(volume_dir: Path, major: int = 18) -> Path:
    """Return the PGDATA path used by official Postgres 18+ images."""
    return volume_dir / str(major) / "docker"


def classify_postgres_volume(volume_dir: Path, target_major: int = 18) -> VolumeLayout:
    """
    Classify a host volume directory for migration decisions.

    Legacy stacks mounted PGDATA at the volume root (Postgres 16 era).
    Postgres 18+ images store PGDATA under ``<major>/docker`` with the bind
    mount at ``/var/lib/postgresql``.
    """
    marker = volume_dir / UPGRADE_MARKER_NAME
    if marker.is_file():
        return VolumeLayout.UPGRADED_MARKER

    pg18_dir = pg18_pgdata_dir(volume_dir, target_major)
    pg18_major = read_pg_major(pg18_dir)
    if pg18_major == target_major:
        return VolumeLayout.PG18
    if pg18_major is not None:
        return VolumeLayout.UNKNOWN

    legacy_major = read_pg_major(volume_dir)
    if legacy_major is not None:
        return VolumeLayout.LEGACY_ROOT

    if not volume_dir.exists():
        return VolumeLayout.EMPTY
    if not any(volume_dir.iterdir()):
        return VolumeLayout.EMPTY
    return VolumeLayout.UNKNOWN


def needs_pg16_to_18_migration(volume_dir: Path, target_major: int = 18) -> bool:
    """True when the volume still holds legacy major-16 (or older) PGDATA at the root."""
    layout = classify_postgres_volume(volume_dir, target_major=target_major)
    if layout != VolumeLayout.LEGACY_ROOT:
        return False
    legacy_major = read_pg_major(volume_dir)
    return legacy_major is not None and legacy_major < target_major


def backup_volume_name(service_volume: str, timestamp: str) -> str:
    """Host directory name for a preserved pre-upgrade data tree."""
    return f"{service_volume}.pg16-backup-{timestamp}"
