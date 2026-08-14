import sqlite3

import pytest

from pib_agent.config import Settings
from pib_agent.db import backup as backup_module
from pib_agent.db.backup import BackupError, backup_database


def _make_db(path, rows=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"row{i}",) for i in range(rows)])
    return path


@pytest.fixture()
def live_db(tmp_path, monkeypatch):
    db = _make_db(tmp_path / "data" / "pib_agent.db")
    settings = Settings(_env_file=None, database_url=f"sqlite:///{db}")
    monkeypatch.setattr(backup_module, "get_settings", lambda: settings)
    return db


def test_backup_produces_a_readable_copy(live_db):
    destination = backup_database()

    assert destination.exists()
    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 3


def test_backup_defaults_next_to_the_database(live_db):
    destination = backup_database()

    assert destination.parent == live_db.parent / "backups"


def test_backup_keeps_only_the_requested_number(live_db, tmp_path):
    backup_dir = tmp_path / "backups"
    # Pre-seed more backups than we intend to keep.
    backup_dir.mkdir(parents=True)
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        (backup_dir / f"pib_agent-{stamp}.db").write_bytes(b"old")

    backup_database(backup_dir=backup_dir, keep=2)

    remaining = sorted(p.name for p in backup_dir.glob("pib_agent-*.db"))
    assert len(remaining) == 2
    # Pruning is newest-first, so the oldest seeded file goes and the fresh one stays.
    assert "pib_agent-20260101T000000Z.db" not in remaining


def test_backup_rejects_non_sqlite_urls(monkeypatch):
    settings = Settings(_env_file=None, database_url="postgresql://localhost/pib")
    monkeypatch.setattr(backup_module, "get_settings", lambda: settings)

    with pytest.raises(BackupError, match="pg_dump"):
        backup_database()


def test_backup_reports_a_missing_database_file(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'nope.db'}")
    monkeypatch.setattr(backup_module, "get_settings", lambda: settings)

    with pytest.raises(BackupError, match="not found"):
        backup_database()


def test_backup_rejects_a_nonsensical_keep(live_db):
    with pytest.raises(BackupError, match="at least 1"):
        backup_database(keep=0)


def test_backup_is_safe_while_the_database_is_being_written(live_db):
    """SQLite's online backup API, not a file copy — a `cp` mid-transaction can corrupt."""
    with sqlite3.connect(live_db) as conn:
        conn.execute("INSERT INTO t (v) VALUES ('uncommitted')")
        destination = backup_database()

    assert destination.exists()
    with sqlite3.connect(destination) as conn:
        conn.execute("SELECT COUNT(*) FROM t").fetchone()
