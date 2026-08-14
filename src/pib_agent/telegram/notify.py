import asyncio
import html
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypedDict

import telegram
from sqlalchemy.orm import Session

from pib_agent.config import get_settings
from pib_agent.db import Article, Enrichment
from pib_agent.db import session_scope as default_session_scope
from pib_agent.telegram.bot import TelegramConfigError
from pib_agent.telegram.subscriptions import (
    get_subscriber_chat_ids,
    remove_all_subscriptions_for_chat,
)

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]

_SendStatus = Literal["ok", "dead", "error"]


class _PendingNotification(TypedDict):
    enrichment_id: int
    article_id: int
    ministry_id: int
    ministry_name: str
    title: str
    summary: str
    upsc_relevant: bool
    source_url: str


@dataclass
class NotifyStats:
    pending: int = 0
    notified_articles: int = 0
    messages_sent: int = 0
    messages_failed: int = 0
    dead_chats_removed: int = 0


def _format_message(
    *, title: str, ministry_name: str, summary: str, upsc_relevant: bool, source_url: str
) -> str:
    badge = " \U0001f393 <b>UPSC</b>" if upsc_relevant else ""
    return (
        f"\U0001f3db <b>{html.escape(ministry_name)}</b>{badge}\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"{html.escape(summary)}\n\n"
        f'<a href="{html.escape(source_url)}">Read the original PIB release</a>'
    )


def _load_pending(session: Session) -> list[_PendingNotification]:
    rows = (
        session.query(Enrichment)
        .join(Article, Article.id == Enrichment.article_id)
        .filter(Enrichment.notified_at.is_(None))
        .order_by(Article.id)
        .all()
    )
    return [
        {
            "enrichment_id": e.id,
            "article_id": e.article_id,
            "ministry_id": e.article.ministry_id,
            "ministry_name": e.article.ministry.name,
            "title": e.article.title,
            "summary": e.summary,
            "upsc_relevant": e.upsc_relevant,
            "source_url": e.article.source_url,
        }
        for e in rows
    ]


async def _send_to_chat(bot: telegram.Bot, chat_id: int, text: str) -> _SendStatus:
    try:
        await bot.send_message(
            chat_id=chat_id, text=text, parse_mode=telegram.constants.ParseMode.HTML
        )
        return "ok"
    except telegram.error.Forbidden:
        logger.warning("Chat %s has blocked the bot; dropping its subscriptions.", chat_id)
        return "dead"
    except telegram.error.BadRequest as exc:
        # Could be a genuinely dead/invalid chat, or a formatting issue on our
        # side — either way it's not safe to assume every subscription for
        # this chat is dead, so we log and count it as a failure, not "dead".
        logger.error("Telegram rejected message to chat %s: %s", chat_id, exc)
        return "error"
    except telegram.error.TelegramError as exc:
        logger.error("Failed to send Telegram message to chat %s: %s", chat_id, exc)
        return "error"


async def _run_notify_async(session_scope: SessionScopeFn) -> NotifyStats:
    settings = get_settings()
    stats = NotifyStats()

    with session_scope() as session:
        pending = _load_pending(session)
    stats.pending = len(pending)

    if not pending:
        return stats

    if not settings.telegram_bot_token:
        raise TelegramConfigError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env before running notify."
        )

    dead_chats: set[int] = set()
    send_count = 0

    async with telegram.Bot(token=settings.telegram_bot_token) as bot:
        for item in pending:
            # Subscribers only want to hear about UPSC-relevant releases —
            # everything else is still marked notified below (so it's never
            # re-checked) but never dispatched.
            chat_ids = (
                get_subscriber_chat_ids(item["ministry_id"], session_scope=session_scope)
                if item["upsc_relevant"]
                else []
            )
            if chat_ids:
                text = _format_message(
                    title=item["title"],
                    ministry_name=item["ministry_name"],
                    summary=item["summary"],
                    upsc_relevant=item["upsc_relevant"],
                    source_url=item["source_url"],
                )
                for chat_id in chat_ids:
                    if chat_id in dead_chats:
                        continue
                    if send_count > 0:
                        await asyncio.sleep(settings.telegram_send_delay_seconds)
                    send_count += 1
                    status = await _send_to_chat(bot, chat_id, text)
                    if status == "ok":
                        stats.messages_sent += 1
                    else:
                        stats.messages_failed += 1
                        if status == "dead":
                            dead_chats.add(chat_id)

            with session_scope() as session:
                enrichment = session.get(Enrichment, item["enrichment_id"])
                if enrichment is not None and enrichment.notified_at is None:
                    enrichment.notified_at = datetime.now(UTC)
            stats.notified_articles += 1

    for chat_id in dead_chats:
        removed = remove_all_subscriptions_for_chat(chat_id, session_scope=session_scope)
        if removed:
            stats.dead_chats_removed += 1
            logger.info("Removed %s dead subscription(s) for chat %s", removed, chat_id)

    return stats


def run_notify(*, session_scope: SessionScopeFn = default_session_scope) -> NotifyStats:
    """Send a Telegram notification for every enriched-but-unnotified,
    UPSC-relevant article to that article's ministry subscribers.

    Non-UPSC-relevant articles are skipped for dispatch but still marked
    notified, same as articles with zero subscribers — a ministry
    subscription is a bet on UPSC-relevant coverage, not a firehose of every
    routine release.

    Idempotent: each article is marked notified (Enrichment.notified_at)
    regardless of whether it had any subscribers, so re-running never
    re-sends. Chats that have blocked the bot have their subscriptions
    dropped automatically.
    """
    return asyncio.run(_run_notify_async(session_scope))
