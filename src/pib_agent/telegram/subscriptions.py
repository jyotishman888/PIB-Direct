"""Ministry subscriptions.

Subscriptions belong to a User now, not to a Telegram chat. The chat_id-facing
helpers here are kept so the bot handlers don't have to care: they resolve the
chat to its user (creating the account on first contact) and operate on that.
Web callers use the *_for_user variants directly.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from sqlalchemy.orm import Session

from pib_agent.auth.service import get_or_create_user_for_telegram
from pib_agent.db import AuthIdentity, Ministry, Subscription
from pib_agent.db import session_scope as default_session_scope

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


@dataclass(frozen=True, slots=True)
class MinistryRef:
    id: int
    name: str
    slug: str


def list_ministries(*, session_scope: SessionScopeFn = default_session_scope) -> list[MinistryRef]:
    with session_scope() as session:
        rows = session.query(Ministry).order_by(Ministry.name).all()
        return [MinistryRef(id=m.id, name=m.name, slug=m.slug) for m in rows]


# --- user-scoped operations (used by the web API) --------------------------


def get_subscribed_ministry_ids_for_user(
    user_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> set[int]:
    with session_scope() as session:
        rows = session.query(Subscription.ministry_id).filter_by(user_id=user_id).all()
        return {row[0] for row in rows}


def toggle_subscription_for_user(
    user_id: int, ministry_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> bool:
    """Subscribe if not already subscribed, else unsubscribe. Returns the new state."""
    with session_scope() as session:
        existing = (
            session.query(Subscription)
            .filter_by(user_id=user_id, ministry_id=ministry_id)
            .one_or_none()
        )
        if existing is not None:
            session.delete(existing)
            return False
        session.add(Subscription(user_id=user_id, ministry_id=ministry_id))
        return True


def set_subscriptions_for_user(
    user_id: int,
    ministry_ids: set[int],
    *,
    session_scope: SessionScopeFn = default_session_scope,
) -> list[MinistryRef]:
    """Replace a user's subscriptions wholesale with `ministry_ids`.

    Unknown ministry ids are ignored rather than erroring, so a stale browser
    tab can't fail the whole save.
    """
    with session_scope() as session:
        valid = {
            row[0] for row in session.query(Ministry.id).filter(Ministry.id.in_(ministry_ids)).all()
        }
        current = {
            row[0] for row in session.query(Subscription.ministry_id).filter_by(user_id=user_id)
        }

        for ministry_id in current - valid:
            session.query(Subscription).filter_by(
                user_id=user_id, ministry_id=ministry_id
            ).delete()
        for ministry_id in valid - current:
            session.add(Subscription(user_id=user_id, ministry_id=ministry_id))

        session.flush()
        rows = (
            session.query(Ministry)
            .join(Subscription, Subscription.ministry_id == Ministry.id)
            .filter(Subscription.user_id == user_id)
            .order_by(Ministry.name)
            .all()
        )
        return [MinistryRef(id=m.id, name=m.name, slug=m.slug) for m in rows]


def list_subscriptions_for_user(
    user_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> list[MinistryRef]:
    with session_scope() as session:
        rows = (
            session.query(Ministry)
            .join(Subscription, Subscription.ministry_id == Ministry.id)
            .filter(Subscription.user_id == user_id)
            .order_by(Ministry.name)
            .all()
        )
        return [MinistryRef(id=m.id, name=m.name, slug=m.slug) for m in rows]


# --- chat-scoped wrappers (used by the Telegram bot) -----------------------


def get_subscribed_ministry_ids(
    chat_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> set[int]:
    user_id = get_or_create_user_for_telegram(chat_id, session_scope=session_scope)
    return get_subscribed_ministry_ids_for_user(user_id, session_scope=session_scope)


def toggle_subscription(
    chat_id: int, ministry_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> bool:
    user_id = get_or_create_user_for_telegram(chat_id, session_scope=session_scope)
    return toggle_subscription_for_user(user_id, ministry_id, session_scope=session_scope)


def subscribe_by_slug(
    chat_id: int, slug: str, *, session_scope: SessionScopeFn = default_session_scope
) -> MinistryRef | None:
    """Subscribe this chat's user to the ministry with this slug; None if unknown."""
    user_id = get_or_create_user_for_telegram(chat_id, session_scope=session_scope)
    with session_scope() as session:
        ministry = session.query(Ministry).filter_by(slug=slug).one_or_none()
        if ministry is None:
            return None
        existing = (
            session.query(Subscription)
            .filter_by(user_id=user_id, ministry_id=ministry.id)
            .one_or_none()
        )
        if existing is None:
            session.add(Subscription(user_id=user_id, ministry_id=ministry.id))
        return MinistryRef(id=ministry.id, name=ministry.name, slug=ministry.slug)


def unsubscribe_by_slug(
    chat_id: int, slug: str, *, session_scope: SessionScopeFn = default_session_scope
) -> MinistryRef | None:
    """Unsubscribe this chat's user from the ministry with this slug; None if unknown."""
    user_id = get_or_create_user_for_telegram(chat_id, session_scope=session_scope)
    with session_scope() as session:
        ministry = session.query(Ministry).filter_by(slug=slug).one_or_none()
        if ministry is None:
            return None
        existing = (
            session.query(Subscription)
            .filter_by(user_id=user_id, ministry_id=ministry.id)
            .one_or_none()
        )
        if existing is not None:
            session.delete(existing)
        return MinistryRef(id=ministry.id, name=ministry.name, slug=ministry.slug)


def list_subscriptions(
    chat_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> list[MinistryRef]:
    user_id = get_or_create_user_for_telegram(chat_id, session_scope=session_scope)
    return list_subscriptions_for_user(user_id, session_scope=session_scope)


def remove_all_subscriptions_for_chat(
    chat_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> int:
    """Drop every subscription for the user behind this chat.

    Used when Telegram tells us a chat has blocked the bot. The account itself
    is left alone — they may still have a Google sign-in and a web session.
    """
    with session_scope() as session:
        identity = (
            session.query(AuthIdentity)
            .filter(AuthIdentity.provider == "telegram", AuthIdentity.subject == str(chat_id))
            .one_or_none()
        )
        if identity is None:
            return 0
        return session.query(Subscription).filter_by(user_id=identity.user_id).delete()


def get_subscriber_chat_ids(
    ministry_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> list[int]:
    """Telegram chats to notify for a ministry.

    Joins through the user's Telegram identity, so someone who signed up with
    Google alone simply isn't in the list until they connect Telegram.
    """
    with session_scope() as session:
        rows = (
            session.query(AuthIdentity.subject)
            .join(Subscription, Subscription.user_id == AuthIdentity.user_id)
            .filter(Subscription.ministry_id == ministry_id, AuthIdentity.provider == "telegram")
            .all()
        )
        return [int(row[0]) for row in rows]
