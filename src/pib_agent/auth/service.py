"""Turning a verified provider token into a User."""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from pib_agent.auth.providers import Provider, ProviderProfile, profile_from_claims
from pib_agent.auth.verify import verify_oidc_token
from pib_agent.config import get_settings
from pib_agent.db import AuthIdentity, User
from pib_agent.db import session_scope as default_session_scope

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


class AuthError(RuntimeError):
    """Sign-in could not be completed."""


class ProviderNotConfiguredError(AuthError):
    """The provider has no client id set, so sign-in through it is unavailable."""


class IdentityAlreadyLinkedError(AuthError):
    """This provider account already belongs to a different user."""


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """A detached snapshot of the signed-in user, safe to use after the session closes."""

    id: int
    display_name: str | None
    email: str | None
    avatar_url: str | None
    providers: tuple[str, ...]


def verify_provider_token(provider: Provider, id_token: str) -> ProviderProfile:
    """Verify a provider's ID token and extract the profile we keep."""
    settings = get_settings()
    client_id = provider.client_id(settings)
    if not client_id:
        raise ProviderNotConfiguredError(
            f"{provider.label} sign-in isn't configured on this server."
        )

    claims = verify_oidc_token(
        id_token,
        issuer=provider.issuer,
        jwks_url=provider.jwks_url,
        audience=client_id,
    )
    return profile_from_claims(provider, claims)


def _snapshot(session: Session, user: User) -> AuthenticatedUser:
    providers = tuple(
        sorted(
            row[0]
            for row in session.query(AuthIdentity.provider)
            .filter(AuthIdentity.user_id == user.id)
            .all()
        )
    )
    return AuthenticatedUser(
        id=user.id,
        display_name=user.display_name,
        email=user.email,
        avatar_url=user.avatar_url,
        providers=providers,
    )


def _apply_profile(user: User, profile: ProviderProfile) -> None:
    """Fill in blanks from the provider without overwriting what we already have."""
    if not user.display_name and profile.display_name:
        user.display_name = profile.display_name
    if not user.email and profile.email:
        user.email = profile.email
    if not user.avatar_url and profile.avatar_url:
        user.avatar_url = profile.avatar_url


def login_with_provider(
    provider: Provider,
    profile: ProviderProfile,
    *,
    session_scope: SessionScopeFn = default_session_scope,
) -> AuthenticatedUser:
    """Sign in, creating the account on first contact.

    Matching is on (provider, subject) only. A Google account and a Telegram
    account are separate users until someone explicitly links them — inferring
    a match from a shared email would let anyone who controls an email address
    take over the account.
    """
    with session_scope() as session:
        identity = (
            session.query(AuthIdentity)
            .filter(AuthIdentity.provider == provider.name, AuthIdentity.subject == profile.subject)
            .one_or_none()
        )

        if identity is not None:
            user = session.get(User, identity.user_id)
            _apply_profile(user, profile)
        else:
            user = User(
                display_name=profile.display_name,
                email=profile.email,
                avatar_url=profile.avatar_url,
            )
            session.add(user)
            session.flush()
            session.add(
                AuthIdentity(user_id=user.id, provider=provider.name, subject=profile.subject)
            )
            logger.info("Created user %s via %s sign-in", user.id, provider.name)

        session.flush()
        return _snapshot(session, user)


def link_identity(
    user_id: int,
    provider: Provider,
    profile: ProviderProfile,
    *,
    session_scope: SessionScopeFn = default_session_scope,
) -> AuthenticatedUser:
    """Attach a second sign-in method to an existing account.

    Refuses an identity already owned by someone else: without that check,
    linking would be a way to take over another person's account.
    """
    with session_scope() as session:
        existing = (
            session.query(AuthIdentity)
            .filter(AuthIdentity.provider == provider.name, AuthIdentity.subject == profile.subject)
            .one_or_none()
        )

        if existing is not None and existing.user_id != user_id:
            raise IdentityAlreadyLinkedError(
                f"That {provider.label} account is already connected to another PIB Direct account."
            )

        user = session.get(User, user_id)
        if user is None:
            raise AuthError("Signed-in user no longer exists.")

        if existing is None:
            session.add(
                AuthIdentity(user_id=user_id, provider=provider.name, subject=profile.subject)
            )
            logger.info("Linked %s identity to user %s", provider.name, user_id)

        _apply_profile(user, profile)
        session.flush()
        return _snapshot(session, user)


def get_user_snapshot(
    user_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> AuthenticatedUser | None:
    with session_scope() as session:
        user = session.get(User, user_id)
        return _snapshot(session, user) if user is not None else None


def get_or_create_user_for_telegram(
    chat_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> int:
    """Resolve a Telegram chat to a user id, creating the account if needed.

    Lets someone use the bot without ever visiting the site: their account
    exists from first contact, and signing in with Telegram on the web later
    lands on the same one, since the widget's `sub` is this same id.
    """
    subject = str(chat_id)
    with session_scope() as session:
        identity = (
            session.query(AuthIdentity)
            .filter(AuthIdentity.provider == "telegram", AuthIdentity.subject == subject)
            .one_or_none()
        )
        if identity is not None:
            return identity.user_id

        user = User(display_name=f"Telegram {chat_id}")
        session.add(user)
        session.flush()
        session.add(AuthIdentity(user_id=user.id, provider="telegram", subject=subject))
        logger.info("Created user %s from Telegram chat %s", user.id, chat_id)
        return user.id
