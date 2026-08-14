from datetime import UTC, datetime, timedelta

import pytest

from pib_agent.auth.providers import GOOGLE, TELEGRAM, ProviderProfile
from pib_agent.auth.service import (
    AuthError,
    IdentityAlreadyLinkedError,
    get_or_create_user_for_telegram,
    link_identity,
    login_with_provider,
)
from pib_agent.auth.sessions import (
    create_session,
    resolve_session,
    revoke_all_sessions_for_user,
    revoke_session,
)
from pib_agent.db.models import AuthIdentity, Ministry, Subscription, User, UserSession
from pib_agent.telegram.subscriptions import (
    get_subscriber_chat_ids,
    list_subscriptions,
    subscribe_by_slug,
)


def _profile(subject: str, **kw) -> ProviderProfile:
    return ProviderProfile(
        subject=subject,
        display_name=kw.get("display_name", "Asha Rao"),
        email=kw.get("email"),
        avatar_url=kw.get("avatar_url"),
    )


# --- sign-in ---------------------------------------------------------------


def test_first_sign_in_creates_a_user_and_identity(session_scope_factory):
    user = login_with_provider(
        GOOGLE,
        _profile("google-sub-1", email="asha@example.com"),
        session_scope=session_scope_factory,
    )

    assert user.providers == ("google",)
    assert user.email == "asha@example.com"
    with session_scope_factory() as s:
        assert s.query(User).count() == 1
        assert s.query(AuthIdentity).count() == 1


def test_signing_in_again_reuses_the_same_account(session_scope_factory):
    profile = _profile("google-sub-1")
    first = login_with_provider(GOOGLE, profile, session_scope=session_scope_factory)
    second = login_with_provider(GOOGLE, profile, session_scope=session_scope_factory)

    assert first.id == second.id
    with session_scope_factory() as s:
        assert s.query(User).count() == 1


def test_different_providers_are_separate_accounts_until_linked(session_scope_factory):
    """Matching on email would let anyone controlling an address take over an account."""
    google_user = login_with_provider(
        GOOGLE, _profile("g-1", email="same@example.com"), session_scope=session_scope_factory
    )
    telegram_user = login_with_provider(
        TELEGRAM, _profile("t-1", email="same@example.com"), session_scope=session_scope_factory
    )

    assert google_user.id != telegram_user.id


def test_sign_in_fills_blank_profile_fields_without_clobbering(session_scope_factory):
    login_with_provider(
        GOOGLE, _profile("g-1", display_name="Asha"), session_scope=session_scope_factory
    )
    user = login_with_provider(
        GOOGLE,
        _profile("g-1", display_name="Renamed", email="later@example.com"),
        session_scope=session_scope_factory,
    )

    assert user.display_name == "Asha"  # existing value kept
    assert user.email == "later@example.com"  # blank filled in


# --- linking ---------------------------------------------------------------


def test_linking_a_second_provider_keeps_one_account(session_scope_factory):
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)

    linked = link_identity(
        user.id, TELEGRAM, _profile("t-1"), session_scope=session_scope_factory
    )

    assert linked.id == user.id
    assert set(linked.providers) == {"google", "telegram"}
    with session_scope_factory() as s:
        assert s.query(User).count() == 1


def test_linking_is_idempotent(session_scope_factory):
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)
    link_identity(user.id, TELEGRAM, _profile("t-1"), session_scope=session_scope_factory)
    link_identity(user.id, TELEGRAM, _profile("t-1"), session_scope=session_scope_factory)

    with session_scope_factory() as s:
        assert s.query(AuthIdentity).filter_by(provider="telegram").count() == 1


def test_linking_someone_elses_identity_is_refused(session_scope_factory):
    """Without this check, linking is an account-takeover primitive."""
    victim = login_with_provider(TELEGRAM, _profile("t-1"), session_scope=session_scope_factory)
    attacker = login_with_provider(GOOGLE, _profile("g-evil"), session_scope=session_scope_factory)

    with pytest.raises(IdentityAlreadyLinkedError):
        link_identity(attacker.id, TELEGRAM, _profile("t-1"), session_scope=session_scope_factory)

    with session_scope_factory() as s:
        identity = s.query(AuthIdentity).filter_by(provider="telegram", subject="t-1").one()
        assert identity.user_id == victim.id


def test_linking_to_a_missing_user_errors(session_scope_factory):
    with pytest.raises(AuthError):
        link_identity(9999, GOOGLE, _profile("g-1"), session_scope=session_scope_factory)


# --- sessions --------------------------------------------------------------


def test_session_round_trip(session_scope_factory):
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)

    token, _expires = create_session(user.id, session_scope=session_scope_factory)
    resolved = resolve_session(token, session_scope=session_scope_factory)

    assert resolved is not None
    assert resolved.id == user.id


def test_raw_session_token_is_never_stored(session_scope_factory):
    """A leaked database shouldn't hand over live sessions."""
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)
    token, _ = create_session(user.id, session_scope=session_scope_factory)

    with session_scope_factory() as s:
        stored = s.query(UserSession).one()
        assert stored.token_hash != token
        assert token not in stored.token_hash


def test_revoked_session_stops_resolving(session_scope_factory):
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)
    token, _ = create_session(user.id, session_scope=session_scope_factory)

    assert revoke_session(token, session_scope=session_scope_factory) is True
    assert resolve_session(token, session_scope=session_scope_factory) is None


def test_expired_session_is_rejected_and_cleaned_up(session_scope_factory):
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)
    token, _ = create_session(user.id, session_scope=session_scope_factory)

    with session_scope_factory() as s:
        s.query(UserSession).one().expires_at = datetime.now(UTC) - timedelta(seconds=1)

    assert resolve_session(token, session_scope=session_scope_factory) is None
    with session_scope_factory() as s:
        assert s.query(UserSession).count() == 0


def test_unknown_and_empty_tokens_resolve_to_nobody(session_scope_factory):
    assert resolve_session(None, session_scope=session_scope_factory) is None
    assert resolve_session("", session_scope=session_scope_factory) is None
    assert resolve_session("nonsense", session_scope=session_scope_factory) is None


def test_revoke_all_signs_out_every_device(session_scope_factory):
    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)
    a, _ = create_session(user.id, session_scope=session_scope_factory)
    b, _ = create_session(user.id, session_scope=session_scope_factory)

    assert revoke_all_sessions_for_user(user.id, session_scope=session_scope_factory) == 2
    assert resolve_session(a, session_scope=session_scope_factory) is None
    assert resolve_session(b, session_scope=session_scope_factory) is None


# --- the bridge between the bot and the web --------------------------------


def test_telegram_chat_resolves_to_a_stable_user(session_scope_factory):
    first = get_or_create_user_for_telegram(900100200, session_scope=session_scope_factory)
    second = get_or_create_user_for_telegram(900100200, session_scope=session_scope_factory)

    assert first == second


def test_bot_subscriber_then_web_sign_in_lands_on_one_account(session_scope_factory):
    """The point of the whole migration.

    Someone subscribes through the bot, later signs in on the web with
    Telegram, and finds their existing subscriptions rather than a blank
    account — because the widget's `sub` is the same id as the chat.
    """
    with session_scope_factory() as s:
        s.add(Ministry(name="Ministry of Finance", slug="ministry-of-finance"))

    subscribe_by_slug(900100200, "ministry-of-finance", session_scope=session_scope_factory)

    web_user = login_with_provider(
        TELEGRAM, _profile("900100200"), session_scope=session_scope_factory
    )

    with session_scope_factory() as s:
        assert s.query(User).count() == 1
        subs = s.query(Subscription).filter_by(user_id=web_user.id).count()
    assert subs == 1
    assert [m.slug for m in list_subscriptions(900100200, session_scope=session_scope_factory)] == [
        "ministry-of-finance"
    ]


def test_google_only_user_is_absent_from_telegram_dispatch(session_scope_factory):
    """No Telegram identity means nothing to send to — not a crash."""
    with session_scope_factory() as s:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        s.add(ministry)
        s.flush()
        ministry_id = ministry.id

    user = login_with_provider(GOOGLE, _profile("g-1"), session_scope=session_scope_factory)
    with session_scope_factory() as s:
        s.add(Subscription(user_id=user.id, ministry_id=ministry_id))

    assert get_subscriber_chat_ids(ministry_id, session_scope=session_scope_factory) == []
