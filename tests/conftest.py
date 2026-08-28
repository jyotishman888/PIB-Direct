from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pib_agent.db.base import Base


@pytest.fixture(autouse=True)
def _isolate_environment_sensitive_settings(monkeypatch):
    """Pin the settings whose real-.env values would break tests.

    Settings reads the developer's actual .env, and that has broken the suite
    three separate times now — SCHEDULER_ENABLED firing real pipeline runs,
    ops alerts messaging a real chat, and SESSION_COOKIE_SECURE=true (set for
    HTTPS) making every session cookie unusable over TestClient's plain http,
    which showed up as unrelated-looking 401s.

    Env vars outrank the .env file in pydantic-settings, so setting them here
    wins without touching the file. The lru_cache has to be cleared either
    side, or a Settings built under different values leaks across tests.
    """
    from pib_agent.config import get_settings

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("OPS_ALERTS_ENABLED", "false")
    # never let a test git-push the operator's repo, whatever their .env says
    monkeypatch.setenv("PUBLISH_ENABLED", "false")
    # ...nor reach the real site: with SITE_URL inherited from .env, publish
    # tests spent 200s each retrying a live 404 before failing.
    monkeypatch.setenv("SITE_URL", "")

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _never_send_real_ops_alerts(monkeypatch):
    """Stop tests from messaging the operator's real Telegram chat.

    `send_ops_alert` reads the developer's actual .env, which has a live bot
    token and admin chat id — so any test that drives a pipeline run to a
    failed/partial state would fire a real alert. Autouse and unconditional:
    the same trap the scheduler set before it was disabled in `api_client`.
    Tests that care about alerting assert against the recorded calls.
    """
    calls: list[tuple[str, str]] = []

    def _record(subject: str, body: str = "") -> bool:
        calls.append((subject, body))
        return True

    monkeypatch.setattr("pib_agent.telegram.alerts.send_ops_alert", _record)
    monkeypatch.setattr("pib_agent.orchestration.pipeline.send_ops_alert", _record)
    return calls


@pytest.fixture()
def ops_alerts(_never_send_real_ops_alerts):
    """The list of (subject, body) alerts raised during a test."""
    return _never_send_real_ops_alerts


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """A Session bound to a fresh in-memory SQLite DB, isolated per test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def session_scope_factory(tmp_path):
    """A session_scope-shaped context manager factory bound to an isolated temp-file DB.

    File-based (rather than :memory:) so that separate connections/transactions
    within the same test (e.g. pipeline code opening several session_scope()
    blocks) all see the same data, matching how the real app behaves.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    @contextmanager
    def _session_scope() -> Iterator[Session]:
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    try:
        yield _session_scope
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def api_client(session_scope_factory, monkeypatch):
    """A FastAPI TestClient wired to the same isolated DB as session_scope_factory.

    Yields (client, session_scope_factory) so a test can seed data through the
    factory and then hit the API and see it.
    """
    from fastapi.testclient import TestClient

    from pib_agent.api import app as app_module
    from pib_agent.api.deps import get_db, get_session_scope

    # `with TestClient(app)` runs the app's real lifespan, which starts the
    # real scheduler based on whatever's in the developer's actual .env
    # (SCHEDULER_ENABLED etc.) — that's read directly, not through FastAPI's
    # DI, so dependency_overrides can't touch it. Tests must never depend on
    # that live config, so it's disabled here unconditionally. (Found the
    # hard way: with SCHEDULER_ENABLED=true locally, every API test used to
    # fire a real, unmocked pipeline run against the real DB on startup.)
    monkeypatch.setattr(app_module, "start_scheduler", lambda: None)
    monkeypatch.setattr(app_module, "stop_scheduler", lambda: None)

    def _override_get_db() -> Iterator[Session]:
        with session_scope_factory() as session:
            yield session

    app_module.app.dependency_overrides[get_db] = _override_get_db
    app_module.app.dependency_overrides[get_session_scope] = lambda: session_scope_factory
    try:
        with TestClient(app_module.app) as client:
            yield client, session_scope_factory
    finally:
        app_module.app.dependency_overrides.pop(get_db, None)
        app_module.app.dependency_overrides.pop(get_session_scope, None)
