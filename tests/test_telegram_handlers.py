from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pib_agent.telegram import handlers
from pib_agent.telegram.subscriptions import MinistryRef

CHAT_ID = 42


def _make_command_update(args: list[str] | None = None):
    """A fake Update+Context pair shaped like an incoming /command message."""
    message = MagicMock()
    message.reply_text = AsyncMock()

    chat = MagicMock()
    chat.id = CHAT_ID

    update = MagicMock()
    update.message = message
    update.effective_message = message
    update.effective_chat = chat
    update.callback_query = None

    context = SimpleNamespace(args=args or [])
    return update, context


def _make_callback_update(data: str):
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()

    chat = MagicMock()
    chat.id = CHAT_ID

    update = MagicMock()
    update.callback_query = query
    update.effective_chat = chat
    update.message = None

    context = SimpleNamespace(args=[])
    return update, context


SENTINEL_KEYBOARD = object()


@pytest.fixture(autouse=True)
def _stub_keyboard(monkeypatch):
    monkeypatch.setattr(handlers, "build_ministries_keyboard", lambda chat_id: SENTINEL_KEYBOARD)


async def test_start_sends_welcome_then_keyboard():
    update, context = _make_command_update()

    await handlers.start(update, context)

    assert update.message.reply_text.call_count == 2
    first_call, second_call = update.message.reply_text.call_args_list
    assert "Welcome" in first_call.args[0]
    assert second_call.kwargs["reply_markup"] is SENTINEL_KEYBOARD


async def test_ministries_command_sends_keyboard():
    update, context = _make_command_update()

    await handlers.ministries_command(update, context)

    update.effective_message.reply_text.assert_awaited_once()
    _, kwargs = update.effective_message.reply_text.call_args
    assert kwargs["reply_markup"] is SENTINEL_KEYBOARD


async def test_toggle_callback_subscribes_and_refreshes_keyboard(monkeypatch):
    update, context = _make_callback_update("toggle:7")
    toggle_calls = []
    monkeypatch.setattr(
        handlers,
        "toggle_subscription",
        lambda chat_id, ministry_id: toggle_calls.append((chat_id, ministry_id)) or True,
    )

    await handlers.toggle_callback(update, context)

    assert toggle_calls == [(CHAT_ID, 7)]
    update.callback_query.answer.assert_awaited_once_with("Subscribed")
    update.callback_query.edit_message_reply_markup.assert_awaited_once_with(
        reply_markup=SENTINEL_KEYBOARD
    )


async def test_toggle_callback_unsubscribe_message(monkeypatch):
    update, context = _make_callback_update("toggle:7")
    monkeypatch.setattr(handlers, "toggle_subscription", lambda chat_id, ministry_id: False)

    await handlers.toggle_callback(update, context)

    update.callback_query.answer.assert_awaited_once_with("Unsubscribed")


async def test_subscribe_command_without_args_shows_usage(monkeypatch):
    update, context = _make_command_update(args=[])
    monkeypatch.setattr(
        handlers,
        "subscribe_by_slug",
        lambda *a, **k: pytest.fail("should not be called without args"),
    )

    await handlers.subscribe_command(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "Usage" in update.message.reply_text.call_args.args[0]


async def test_subscribe_command_unknown_slug(monkeypatch):
    update, context = _make_command_update(args=["not-real"])
    monkeypatch.setattr(handlers, "subscribe_by_slug", lambda chat_id, slug: None)

    await handlers.subscribe_command(update, context)

    assert "Unknown ministry slug" in update.message.reply_text.call_args.args[0]


async def test_subscribe_command_success(monkeypatch):
    update, context = _make_command_update(args=["Ministry-Of-Finance"])
    seen_slugs = []

    def fake_subscribe(chat_id, slug):
        seen_slugs.append(slug)
        return MinistryRef(id=1, name="Ministry of Finance", slug="ministry-of-finance")

    monkeypatch.setattr(handlers, "subscribe_by_slug", fake_subscribe)

    await handlers.subscribe_command(update, context)

    assert seen_slugs == ["ministry-of-finance"]  # lowercased before lookup
    assert "Subscribed to Ministry of Finance" in update.message.reply_text.call_args.args[0]


async def test_unsubscribe_command_success(monkeypatch):
    update, context = _make_command_update(args=["ministry-of-finance"])
    monkeypatch.setattr(
        handlers,
        "unsubscribe_by_slug",
        lambda chat_id, slug: MinistryRef(id=1, name="Ministry of Finance", slug=slug),
    )

    await handlers.unsubscribe_command(update, context)

    assert "Unsubscribed from Ministry of Finance" in update.message.reply_text.call_args.args[0]


async def test_mysubs_command_empty(monkeypatch):
    update, context = _make_command_update()
    monkeypatch.setattr(handlers, "list_subscriptions", lambda chat_id: [])

    await handlers.mysubs_command(update, context)

    assert "not subscribed" in update.message.reply_text.call_args.args[0]


async def test_mysubs_command_with_subscriptions(monkeypatch):
    update, context = _make_command_update()
    monkeypatch.setattr(
        handlers,
        "list_subscriptions",
        lambda chat_id: [
            MinistryRef(id=1, name="Ministry of Defence", slug="ministry-of-defence"),
            MinistryRef(id=2, name="Ministry of Finance", slug="ministry-of-finance"),
        ],
    )

    await handlers.mysubs_command(update, context)

    text = update.message.reply_text.call_args.args[0]
    assert "Ministry of Defence" in text
    assert "Ministry of Finance" in text
