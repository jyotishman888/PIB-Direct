import pytest

from pib_agent.config import Settings
from pib_agent.db import diagnostics as diag
from pib_agent.db.diagnostics import (
    DatabaseNotReadyError,
    check_database_ready,
    describe_database,
    wait_for_database,
)


def _settings(url: str) -> Settings:
    return Settings(_env_file=None, database_url=url)


def test_describe_database_never_leaks_the_password(monkeypatch):
    """This string goes to logs, which get pasted into chats and issue trackers."""
    url = "postgresql+psycopg://appuser:sup3r-s3cret@db.internal:5432/railway"
    monkeypatch.setattr(diag, "get_settings", lambda: _settings(url))

    described = describe_database()

    assert "sup3r-s3cret" not in described
    assert "appuser" not in described
    assert "db.internal:5432/railway" in described


def test_describe_database_names_the_sqlite_file(monkeypatch):
    monkeypatch.setattr(diag, "get_settings", lambda: _settings("sqlite:///data/pib_agent.db"))

    assert "sqlite" in describe_database()
    assert "data/pib_agent.db" in describe_database()


def test_missing_schema_on_sqlite_blames_the_likely_cause(monkeypatch, tmp_path):
    """The first deploy failed exactly this way, with an unhelpful traceback.

    DATABASE_URL never reached the container, Settings fell back to SQLite,
    migrations ran against ephemeral storage, and the app crashed with a bare
    "no such table: pipeline_runs". The message should name that.
    """
    from sqlalchemy import create_engine

    empty_db = tmp_path / "empty.db"
    monkeypatch.setattr(diag, "get_settings", lambda: _settings(f"sqlite:///{empty_db}"))

    import pib_agent.db.base as base_module

    monkeypatch.setattr(base_module, "engine", create_engine(f"sqlite:///{empty_db}"))

    with pytest.raises(DatabaseNotReadyError) as excinfo:
        check_database_ready()

    message = str(excinfo.value)
    assert "DATABASE_URL" in message
    assert "ephemeral" in message


def test_ready_database_passes(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    from pib_agent.db.base import Base

    db = tmp_path / "ready.db"
    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)

    monkeypatch.setattr(diag, "get_settings", lambda: _settings(f"sqlite:///{db}"))

    import pib_agent.db.base as base_module

    monkeypatch.setattr(base_module, "engine", engine)

    check_database_ready()  # must not raise


def test_unreachable_database_is_reported_clearly(monkeypatch):
    from sqlalchemy import create_engine

    url = "postgresql+psycopg://u:p@127.0.0.1:1/none"
    monkeypatch.setattr(diag, "get_settings", lambda: _settings(url))

    import pib_agent.db.base as base_module

    monkeypatch.setattr(
        base_module, "engine", create_engine(url, connect_args={"connect_timeout": 1})
    )

    with pytest.raises(DatabaseNotReadyError, match="Could not connect"):
        check_database_ready()

def test_wait_returns_once_the_database_is_reachable(monkeypatch, tmp_path):
    from sqlalchemy import create_engine

    import pib_agent.db.base as base_module

    db = tmp_path / "reachable.db"
    monkeypatch.setattr(diag, "get_settings", lambda: _settings(f"sqlite:///{db}"))
    monkeypatch.setattr(base_module, "engine", create_engine(f"sqlite:///{db}"))

    wait_for_database(timeout_seconds=5, interval_seconds=0.1)  # must not raise


def test_wait_gives_up_with_a_clear_message(monkeypatch):
    """Retrying covers the private network coming up late; it can't cover a
    genuinely wrong host, so the give-up path has to say so plainly."""
    from sqlalchemy import create_engine

    import pib_agent.db.base as base_module

    url = "postgresql+psycopg://u:p@127.0.0.1:1/none"
    monkeypatch.setattr(diag, "get_settings", lambda: _settings(url))
    monkeypatch.setattr(
        base_module, "engine", create_engine(url, connect_args={"connect_timeout": 1})
    )

    with pytest.raises(DatabaseNotReadyError, match="unreachable after"):
        wait_for_database(timeout_seconds=2, interval_seconds=0.1)
