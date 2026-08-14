"""Server-side browser sessions.

Opaque random tokens rather than JWT cookies, so a session can be revoked the
moment it needs to be — which matters as soon as anything is paid for. Only
the SHA-256 hash of a token is stored, so a leaked database doesn't hand over
usable sessions.
"""

import hashlib
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from pib_agent.config import get_settings
from pib_agent.db import User, UserSession
from pib_agent.db import session_scope as default_session_scope

SessionScopeFn = Callable[[], AbstractContextManager[Session]]

_TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    user_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> tuple[str, datetime]:
    """Open a session for a user. Returns (raw token, expiry).

    The raw token is returned once and never stored — it goes straight into
    the cookie.
    """
    settings = get_settings()
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = datetime.now(UTC) + timedelta(days=settings.session_ttl_days)

    with session_scope() as session:
        session.add(
            UserSession(user_id=user_id, token_hash=hash_token(token), expires_at=expires_at)
        )

    return token, expires_at


def resolve_session(
    token: str | None, *, session_scope: SessionScopeFn = default_session_scope
) -> User | None:
    """Return the signed-in user for a session token, or None.

    Expired sessions resolve to None and are deleted on sight, so the table
    doesn't accumulate dead rows without needing a sweeper job.
    """
    if not token:
        return None

    with session_scope() as session:
        record = (
            session.query(UserSession).filter(UserSession.token_hash == hash_token(token)).first()
        )
        if record is None:
            return None

        expires_at = record.expires_at
        if expires_at.tzinfo is None:  # SQLite hands back naive datetimes
            expires_at = expires_at.replace(tzinfo=UTC)

        now = datetime.now(UTC)
        if expires_at <= now:
            session.delete(record)
            return None

        record.last_seen_at = now
        user = session.get(User, record.user_id)
        if user is not None:
            user.last_seen_at = now
            session.expunge(user)
        return user


def revoke_session(
    token: str | None, *, session_scope: SessionScopeFn = default_session_scope
) -> bool:
    """Delete a session. Returns True if one was actually removed."""
    if not token:
        return False

    with session_scope() as session:
        deleted = (
            session.query(UserSession).filter(UserSession.token_hash == hash_token(token)).delete()
        )
        return bool(deleted)


def revoke_all_sessions_for_user(
    user_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> int:
    """Sign a user out everywhere (e.g. after unlinking a provider)."""
    with session_scope() as session:
        return session.query(UserSession).filter(UserSession.user_id == user_id).delete()
