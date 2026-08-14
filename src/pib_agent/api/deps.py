from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from pib_agent.auth.service import AuthenticatedUser, get_user_snapshot
from pib_agent.auth.sessions import resolve_session
from pib_agent.config import get_settings
from pib_agent.db import session_scope

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def get_session_scope() -> SessionScopeFn:
    """The session_scope factory pipelines use internally (own multiple sessions per run).

    Kept as its own dependency (distinct from get_db's single per-request
    Session) so tests can override it to point orchestration runs at the same
    isolated DB the rest of a test uses.
    """
    return session_scope


def get_current_user(
    request: Request, scope: SessionScopeFn = Depends(get_session_scope)
) -> AuthenticatedUser | None:
    """The signed-in user, or None. Never raises — for endpoints open to anonymous readers."""
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    user = resolve_session(token, session_scope=scope)
    if user is None:
        return None
    return get_user_snapshot(user.id, session_scope=scope)


def require_user(
    user: AuthenticatedUser | None = Depends(get_current_user),
) -> AuthenticatedUser:
    """The signed-in user, or a 401. For anything that touches personal data."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to do that."
        )
    return user
