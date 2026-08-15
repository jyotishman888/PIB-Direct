"""Startup checks that turn confusing database failures into obvious ones."""

import logging
import time

from sqlalchemy import inspect, text

from pib_agent.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseNotReadyError(RuntimeError):
    """The configured database isn't usable — usually misconfiguration, not a bug."""


def describe_database() -> str:
    """A credential-free description of what we're actually connected to."""
    url = get_settings().database_url
    if url.startswith("sqlite"):
        return f"sqlite ({url.removeprefix('sqlite:///') or ':memory:'})"

    # Never log the password: scheme://user:pass@host/name -> scheme://host/name
    try:
        scheme, rest = url.split("://", 1)
        host_and_name = rest.rsplit("@", 1)[-1]
        return f"{scheme} ({host_and_name})"
    except ValueError:  # pragma: no cover - defensive
        return "unrecognised database url"


def wait_for_database(timeout_seconds: float = 60.0, interval_seconds: float = 2.0) -> None:
    """Block until the database accepts a connection, or give up loudly.

    Managed platforms bring the private network up *after* the container
    starts — Railway's docs are explicit that private networking is
    runtime-only — so the first connection attempt of a freshly started
    container can time out purely because the mesh isn't attached yet.
    Retrying briefly turns that race into a non-event; without it, the very
    first deploy of the day fails on a cold network.
    """
    from pib_agent.db.base import engine

    target = describe_database()
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        attempt += 1
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            if attempt > 1:
                logger.info("Database reachable after %s attempt(s): %s", attempt, target)
            return
        except Exception as exc:
            last_error = exc
            logger.info(
                "Database not reachable yet (attempt %s) — %s. Retrying...", attempt, target
            )
            time.sleep(interval_seconds)

    raise DatabaseNotReadyError(
        f"Database unreachable after {timeout_seconds:.0f}s — {target}. "
        f"Last error: {last_error}"
    )


def check_database_ready() -> None:
    """Fail loudly, and usefully, if the database isn't set up.

    Two failure modes this exists for, both learned the hard way on the first
    deploy:

    1. `DATABASE_URL` never reaches the container, so Settings falls back to
       its local SQLite default. Migrations then "succeed" against a file in
       ephemeral container storage and the app starts against a different,
       empty one — surfacing as a bare "no such table: pipeline_runs"
       traceback that says nothing about the actual cause.
    2. Migrations simply haven't been run yet.

    Both used to produce a SQLAlchemy stack trace. Now they produce a sentence
    naming the likely cause.
    """
    from pib_agent.db.base import engine

    target = describe_database()

    try:
        tables = set(inspect(engine).get_table_names())
    except Exception as exc:
        raise DatabaseNotReadyError(f"Could not connect to the database — {target}: {exc}") from exc

    if "pipeline_runs" in tables:
        logger.info("Database ready: %s", target)
        return

    hint = "Run `alembic upgrade head` against it."
    if get_settings().database_url.startswith("sqlite"):
        hint = (
            "This is the built-in SQLite fallback, which usually means DATABASE_URL "
            "isn't set in this environment. On a deployed service that file lives in "
            "ephemeral storage, so migrations and the app end up looking at different "
            "databases. Set DATABASE_URL, or run `alembic upgrade head` if you meant "
            "to use SQLite."
        )

    raise DatabaseNotReadyError(f"Database has no schema — {target}. {hint}")
