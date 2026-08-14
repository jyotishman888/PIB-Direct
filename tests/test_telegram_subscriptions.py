from pib_agent.db.models import Ministry
from pib_agent.telegram.subscriptions import (
    get_subscribed_ministry_ids,
    get_subscriber_chat_ids,
    list_ministries,
    list_subscriptions,
    remove_all_subscriptions_for_chat,
    subscribe_by_slug,
    toggle_subscription,
    unsubscribe_by_slug,
)

CHAT_ID = 123456789


def _seed_ministries(session_scope_factory) -> tuple[int, int]:
    with session_scope_factory() as session:
        finance = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        defence = Ministry(name="Ministry of Defence", slug="ministry-of-defence")
        session.add_all([finance, defence])
        session.flush()
        return finance.id, defence.id


def test_list_ministries_alphabetical(session_scope_factory):
    _seed_ministries(session_scope_factory)

    ministries = list_ministries(session_scope=session_scope_factory)

    assert [m.name for m in ministries] == ["Ministry of Defence", "Ministry of Finance"]


def test_toggle_subscription_subscribes_then_unsubscribes(session_scope_factory):
    finance_id, _ = _seed_ministries(session_scope_factory)

    first = toggle_subscription(CHAT_ID, finance_id, session_scope=session_scope_factory)
    assert first is True
    assert get_subscribed_ministry_ids(CHAT_ID, session_scope=session_scope_factory) == {
        finance_id
    }

    second = toggle_subscription(CHAT_ID, finance_id, session_scope=session_scope_factory)
    assert second is False
    assert get_subscribed_ministry_ids(CHAT_ID, session_scope=session_scope_factory) == set()


def test_subscribe_by_slug_unknown_returns_none(session_scope_factory):
    _seed_ministries(session_scope_factory)

    result = subscribe_by_slug(CHAT_ID, "not-a-real-ministry", session_scope=session_scope_factory)

    assert result is None


def test_subscribe_by_slug_is_idempotent(session_scope_factory):
    _seed_ministries(session_scope_factory)

    first = subscribe_by_slug(CHAT_ID, "ministry-of-finance", session_scope=session_scope_factory)
    second = subscribe_by_slug(CHAT_ID, "ministry-of-finance", session_scope=session_scope_factory)

    assert first is not None
    assert first.name == "Ministry of Finance"
    assert second is not None

    subs = list_subscriptions(CHAT_ID, session_scope=session_scope_factory)
    assert len(subs) == 1  # no duplicate row from subscribing twice


def test_unsubscribe_by_slug(session_scope_factory):
    _seed_ministries(session_scope_factory)
    subscribe_by_slug(CHAT_ID, "ministry-of-finance", session_scope=session_scope_factory)

    result = unsubscribe_by_slug(
        CHAT_ID, "ministry-of-finance", session_scope=session_scope_factory
    )

    assert result is not None
    assert list_subscriptions(CHAT_ID, session_scope=session_scope_factory) == []


def test_unsubscribe_by_slug_when_not_subscribed_is_a_noop(session_scope_factory):
    _seed_ministries(session_scope_factory)

    result = unsubscribe_by_slug(
        CHAT_ID, "ministry-of-finance", session_scope=session_scope_factory
    )

    assert result is not None  # ministry exists, just wasn't subscribed
    assert list_subscriptions(CHAT_ID, session_scope=session_scope_factory) == []


def test_list_subscriptions_returns_only_this_chats_ministries(session_scope_factory):
    finance_id, defence_id = _seed_ministries(session_scope_factory)
    other_chat = 999
    toggle_subscription(CHAT_ID, finance_id, session_scope=session_scope_factory)
    toggle_subscription(other_chat, defence_id, session_scope=session_scope_factory)

    subs = list_subscriptions(CHAT_ID, session_scope=session_scope_factory)

    assert [m.slug for m in subs] == ["ministry-of-finance"]


def test_get_subscriber_chat_ids(session_scope_factory):
    finance_id, _ = _seed_ministries(session_scope_factory)
    toggle_subscription(CHAT_ID, finance_id, session_scope=session_scope_factory)
    toggle_subscription(555, finance_id, session_scope=session_scope_factory)

    chat_ids = get_subscriber_chat_ids(finance_id, session_scope=session_scope_factory)

    assert set(chat_ids) == {CHAT_ID, 555}


def test_remove_all_subscriptions_for_chat(session_scope_factory):
    finance_id, defence_id = _seed_ministries(session_scope_factory)
    toggle_subscription(CHAT_ID, finance_id, session_scope=session_scope_factory)
    toggle_subscription(CHAT_ID, defence_id, session_scope=session_scope_factory)

    removed = remove_all_subscriptions_for_chat(CHAT_ID, session_scope=session_scope_factory)

    assert removed == 2
    assert list_subscriptions(CHAT_ID, session_scope=session_scope_factory) == []
