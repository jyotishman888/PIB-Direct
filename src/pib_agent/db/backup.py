"""Point-in-time backups of the SQLite database.

The corpus is expensive to rebuild — every enrichment in it was paid for
once — and it currently lives as a single file on a single disk with no
copy anywhere.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pib_agent.config import get_settings

logger = logging.getLogger(__name__)

_SQLITE_PREFIX = "sqlite:///"


class BackupError(RuntimeError):
    """Raised when a backup can't be taken."""


def _sqlite_path(database_url: str) -> Path:
    if not database_url.startswith(_SQLITE_PREFIX):
        raise BackupError(
            f"Only SQLite databases can be backed up by this command (got {database_url!r}). "
            "On Postgres, use pg_dump instead."
        )
    return Path(database_url[len(_SQLITE_PREFIX) :])


def _prune(backup_dir: Path, keep: int) -> list[Path]:
    existing = sorted(backup_dir.glob("pib_agent-*.db"), reverse=True)
    removed = []
    for stale in existing[keep:]:
        stale.unlink()
        removed.append(stale)
    return removed


def backup_database(*, backup_dir: Path | None = None, keep: int = 7) -> Path:
    """Copy the live DB to a timestamped file and prune old copies.

    Uses SQLite's online backup API rather than a filesystem copy, so it's
    safe to run while the app is mid-write — a plain `cp` of a database with
    an active transaction can produce a corrupt file.
    """
    if keep < 1:
        raise BackupError("keep must be at least 1.")

    settings = get_settings()
    source = _sqlite_path(settings.database_url)
    if not source.exists():
        raise BackupError(f"Database file not found: {source}")

    backup_dir = backup_dir or source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = backup_dir / f"pib_agent-{stamp}.db"

    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)

    removed = _prune(backup_dir, keep)
    logger.info(
        "Backed up database to %s (%.1f MB); pruned %s old backup(s)",
        destination,
        destination.stat().st_size / 1_048_576,
        len(removed),
    )
    return destination
