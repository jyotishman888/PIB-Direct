"""The "only one pipeline run at a time" guard.

A `threading.Lock` is enough while everything runs in one process, which is
true locally. It stops being enough the moment the app is deployed: a rolling
deploy briefly runs the old and new instances together, and each would fire
its own startup pipeline run — duplicating Claude enrichment spend and sending
every subscriber two copies of the same release.

On Postgres the lock therefore moves into the database as a session-level
advisory lock, which is visible to every instance. On SQLite (local dev) the
in-process lock is kept, since there's only ever one process.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from threading import Lock

from sqlalchemy import text
from sqlalchemy.orm import Session

from pib_agent.config import get_settings

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]

# Arbitrary but fixed: advisory locks are keyed by number, and every instance
# must agree on which number means "the pipeline".
_ADVISORY_LOCK_KEY = 4_155_711_001

_thread_lock = Lock()


def _is_postgres() -> bool:
    return get_settings().database_url.startswith("postgresql")


class RunLock:
    """Holds whichever lock the current database supports.

    A Postgres advisory lock is session-scoped, so the connection that took it
    has to be the one that releases it — which is why the connection is held
    open for the duration rather than borrowed per statement.
    """

    def __init__(self) -> None:
        self._connection = None
        self._held_thread_lock = False

    def acquire(self) -> bool:
        """Try to take the lock. Returns False rather than blocking."""
        if not _is_postgres():
            self._held_thread_lock = _thread_lock.acquire(blocking=False)
            return self._held_thread_lock

        from pib_agent.db.base import engine

        connection = engine.connect()
        try:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
                ).scalar()
            )
        except Exception:
            connection.close()
            raise

        if not acquired:
            connection.close()
            return False

        self._connection = connection
        return True

    def release(self) -> None:
        if self._held_thread_lock:
            _thread_lock.release()
            self._held_thread_lock = False

        if self._connection is not None:
            try:
                self._connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY}
                )
                self._connection.commit()
            except Exception:
                # Losing the connection releases the lock anyway (advisory
                # locks die with their session), so this must not mask the
                # pipeline's own outcome.
                logger.warning("Could not release the advisory run lock cleanly.", exc_info=True)
            finally:
                self._connection.close()
                self._connection = None
