from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from pib_agent.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    connect_args: dict = {}
    kwargs: dict = {}

    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        db_path = settings.database_url.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            from pathlib import Path

            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    else:
        # Managed Postgres closes idle connections (and a deploy or failover
        # kills them all), which surfaces as a stale-connection error on the
        # first query after a quiet spell. pool_pre_ping tests a connection
        # before handing it out, so that failure becomes a transparent
        # reconnect instead. Modest pool: this runs a single web instance
        # plus a bot, not a fleet.
        kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=1800)

    return create_engine(settings.database_url, connect_args=connect_args, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
