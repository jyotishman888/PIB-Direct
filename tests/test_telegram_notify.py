from datetime import datetime

import pytest
import telegram.error

from pib_agent.db.models import Article, Enrichment, Ministry
from pib_agent.telegram import notify as notify_module
from pib_agent.telegram.bot import TelegramConfigError
from pib_agent.telegram.notify import run_notify
from pib_agent.telegram.subscriptions import subscribe_by_slug


def _fake_settings(*, telegram_bot_token: str | None):
    """A minimal settings stand-in exposing just what notify.py reads."""
    return type(
        "FakeSettings",
        (),
        {"telegram_bot_token": telegram_bot_token, "telegram_send_delay_seconds": 0.0},
    )()


class _FakeBot:
    """Records every send_message call; raises a canned exception per chat_id."""

    def __init__(self, *, token: str | None = None, responses: dict[int, Exception] | None = None):
        self.token = token
        self.responses = responses or {}
        self.sent: list[tuple[int, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def send_message(self, *, chat_id, text, parse_mode=None):
        self.sent.append((chat_id, text))
        outcome = self.responses.get(chat_id)
        if outcome is not None:
            raise outcome


def _make_fake_bot_class(responses: dict[int, Exception] | None = None):
    shared: list[_FakeBot] = []

    class _Factory:
        def __call__(self, *, token=None):
            bot = _FakeBot(token=token, responses=responses)
            shared.append(bot)
            return bot

    factory = _Factory()
    factory.instances = shared
    return factory


def _seed_article_with_enrichment(
    session_scope_factory,
    *,
    prid: int,
    ministry_name: str = "Ministry of Finance",
    ministry_slug: str = "ministry-of-finance",
    upsc_relevant: bool = True,
) -> int:
    with session_scope_factory() as session:
        ministry = (
            session.query(Ministry).filter_by(slug=ministry_slug).one_or_none()
            or Ministry(name=ministry_name, slug=ministry_slug)
        )
        article = Article(
            prid=prid,
            ministry=ministry,
            title=f"Release {prid}",
            subtitle=None,
            body_text="Body.",
            body_html="<p>Body.</p>",
            pib_office="PIB Delhi",
            release_datetime=datetime(2026, 8, 9, 12, 0),
            source_url=f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}",
        )
        session.add(article)
        session.flush()
        session.add(
            Enrichment(
                article_id=article.id,
                summary=f"Summary {prid}.",
                context="Context.",
                upsc_relevant=upsc_relevant,
                syllabus_topics=[],
                prelims_questions=[],
                mains_questions=[],
                model="claude-sonnet-5",
            )
        )
        return article.id


def _subscribe(session_scope_factory, chat_id: int, ministry_slug: str) -> None:
    """Subscribe through the same path the bot uses.

    Subscriptions hang off a User now, not a chat id, so going through
    subscribe_by_slug also exercises the chat -> user resolution rather than
    quietly constructing a row the bot could never produce.
    """
    subscribe_by_slug(chat_id, ministry_slug, session_scope=session_scope_factory)


def test_run_notify_with_nothing_pending_requires_no_token(monkeypatch, session_scope_factory):
    fake_settings = _fake_settings(telegram_bot_token=None)
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.pending == 0
    assert stats.messages_sent == 0


def test_run_notify_raises_without_token_when_articles_are_pending(
    monkeypatch, session_scope_factory
):
    _seed_article_with_enrichment(session_scope_factory, prid=1)
    fake_settings = _fake_settings(telegram_bot_token=None)
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)

    with pytest.raises(TelegramConfigError):
        run_notify(session_scope=session_scope_factory)


def test_run_notify_sends_to_subscribers_and_marks_notified(monkeypatch, session_scope_factory):
    article_id = _seed_article_with_enrichment(session_scope_factory, prid=1)
    _subscribe(session_scope_factory, chat_id=111, ministry_slug="ministry-of-finance")
    _subscribe(session_scope_factory, chat_id=222, ministry_slug="ministry-of-finance")

    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class()
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.pending == 1
    assert stats.notified_articles == 1
    assert stats.messages_sent == 2
    assert stats.messages_failed == 0

    bot = fake_bot_factory.instances[0]
    sent_chat_ids = {chat_id for chat_id, _ in bot.sent}
    assert sent_chat_ids == {111, 222}
    assert "Release 1" in bot.sent[0][1]
    assert "\U0001f393" in bot.sent[0][1]  # UPSC badge present

    with session_scope_factory() as session:
        enrichment = session.query(Enrichment).filter_by(article_id=article_id).one()
        assert enrichment.notified_at is not None


def test_run_notify_skips_non_upsc_relevant_articles_but_marks_notified(
    monkeypatch, session_scope_factory
):
    article_id = _seed_article_with_enrichment(session_scope_factory, prid=1, upsc_relevant=False)
    _subscribe(session_scope_factory, chat_id=111, ministry_slug="ministry-of-finance")

    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class()
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.pending == 1
    assert stats.notified_articles == 1
    assert stats.messages_sent == 0
    if fake_bot_factory.instances:
        assert fake_bot_factory.instances[0].sent == []

    with session_scope_factory() as session:
        enrichment = session.query(Enrichment).filter_by(article_id=article_id).one()
        assert enrichment.notified_at is not None


def test_run_notify_sends_only_upsc_relevant_among_mixed_pending(
    monkeypatch, session_scope_factory
):
    _seed_article_with_enrichment(session_scope_factory, prid=1, upsc_relevant=False)
    _seed_article_with_enrichment(session_scope_factory, prid=2, upsc_relevant=True)
    _subscribe(session_scope_factory, chat_id=111, ministry_slug="ministry-of-finance")

    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class()
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.pending == 2
    assert stats.notified_articles == 2
    assert stats.messages_sent == 1

    bot = fake_bot_factory.instances[0]
    assert len(bot.sent) == 1
    assert "Release 2" in bot.sent[0][1]


def test_run_notify_with_no_subscribers_still_marks_notified(monkeypatch, session_scope_factory):
    _seed_article_with_enrichment(session_scope_factory, prid=1)
    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class()
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.notified_articles == 1
    assert stats.messages_sent == 0
    # No Bot should even need to be constructed just to discover 0 subscribers,
    # but if it is, it must not have sent anything.
    if fake_bot_factory.instances:
        assert fake_bot_factory.instances[0].sent == []


def test_run_notify_is_idempotent(monkeypatch, session_scope_factory):
    _seed_article_with_enrichment(session_scope_factory, prid=1)
    _subscribe(session_scope_factory, chat_id=111, ministry_slug="ministry-of-finance")
    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class()
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    first = run_notify(session_scope=session_scope_factory)
    second = run_notify(session_scope=session_scope_factory)

    assert first.messages_sent == 1
    assert second.pending == 0
    assert second.messages_sent == 0


def test_run_notify_removes_subscriptions_for_forbidden_chat(monkeypatch, session_scope_factory):
    _seed_article_with_enrichment(session_scope_factory, prid=1)
    _subscribe(session_scope_factory, chat_id=111, ministry_slug="ministry-of-finance")
    _subscribe(session_scope_factory, chat_id=222, ministry_slug="ministry-of-finance")

    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class(
        responses={111: telegram.error.Forbidden("bot was blocked by the user")}
    )
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.messages_sent == 1  # chat 222 succeeded
    assert stats.messages_failed == 1  # chat 111 failed
    assert stats.dead_chats_removed == 1

    from pib_agent.telegram.subscriptions import list_subscriptions

    assert list_subscriptions(111, session_scope=session_scope_factory) == []
    assert len(list_subscriptions(222, session_scope=session_scope_factory)) == 1


def test_run_notify_bad_request_does_not_remove_subscription(monkeypatch, session_scope_factory):
    _seed_article_with_enrichment(session_scope_factory, prid=1)
    _subscribe(session_scope_factory, chat_id=111, ministry_slug="ministry-of-finance")

    fake_settings = _fake_settings(telegram_bot_token="test-token")
    monkeypatch.setattr(notify_module, "get_settings", lambda: fake_settings)
    fake_bot_factory = _make_fake_bot_class(
        responses={111: telegram.error.BadRequest("something else went wrong")}
    )
    monkeypatch.setattr(notify_module.telegram, "Bot", fake_bot_factory)

    stats = run_notify(session_scope=session_scope_factory)

    assert stats.messages_failed == 1
    assert stats.dead_chats_removed == 0

    from pib_agent.telegram.subscriptions import list_subscriptions

    assert len(list_subscriptions(111, session_scope=session_scope_factory)) == 1
