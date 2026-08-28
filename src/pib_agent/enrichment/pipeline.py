import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from sqlalchemy.orm import Session

from pib_agent.config import get_settings
from pib_agent.db import Article, Enrichment
from pib_agent.db import session_scope as default_session_scope
from pib_agent.enrichment.client import (
    EnrichmentBlockedError,
    EnrichmentError,
    enrich_article,
)

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


class _PendingArticle(TypedDict):
    id: int
    title: str
    subtitle: str | None
    body_text: str
    ministry_name: str
    release_datetime: datetime | None
    pib_office: str | None


@dataclass
class EnrichStats:
    pending: int = 0
    enriched: int = 0
    failed: int = 0
    failed_article_ids: list[int] = field(default_factory=list)
    # Set when the pass stopped early because the account, not the article,
    # was the problem. Carries the reason so the ops alert names it.
    blocked: str | None = None


def _load_pending_articles(session: Session) -> list[_PendingArticle]:
    rows = (
        session.query(Article)
        .outerjoin(Enrichment, Enrichment.article_id == Article.id)
        .filter(Enrichment.id.is_(None))
        .all()
    )
    return [
        {
            "id": article.id,
            "title": article.title,
            "subtitle": article.subtitle,
            "body_text": article.body_text,
            "ministry_name": article.ministry.name,
            "release_datetime": article.release_datetime,
            "pib_office": article.pib_office,
        }
        for article in rows
    ]


def _enrich_one(
    article: _PendingArticle, session_scope: SessionScopeFn, stats: EnrichStats
) -> None:
    try:
        result = enrich_article(
            title=article["title"],
            ministry_name=article["ministry_name"],
            subtitle=article["subtitle"],
            body_text=article["body_text"],
            release_datetime=article["release_datetime"],
            pib_office=article["pib_office"],
        )
    except EnrichmentBlockedError:
        raise
    except EnrichmentError as exc:
        logger.error("Failed to enrich article id=%s: %s", article["id"], exc)
        stats.failed += 1
        stats.failed_article_ids.append(article["id"])
        return

    settings = get_settings()
    # Claude rates study-worthiness 1-5; the relevant/not-relevant boolean the
    # dashboard filter and Telegram notify both read is derived here rather
    # than asked for directly, so the cutoff is one config change instead of a
    # prompt rewrite and a full re-enrichment.
    upsc_relevant = result.upsc_relevance >= settings.upsc_relevance_threshold

    with session_scope() as session:
        # Re-check inside the transaction in case of a concurrent/overlapping enrich run.
        if session.query(Enrichment).filter_by(article_id=article["id"]).one_or_none() is not None:
            return

        session.add(
            Enrichment(
                article_id=article["id"],
                summary=result.summary,
                context=result.context,
                upsc_relevance=result.upsc_relevance,
                upsc_relevant=upsc_relevant,
                syllabus_topics=result.syllabus_topics,
                prelims_questions=[q.model_dump() for q in result.prelims_questions],
                mains_questions=[q.model_dump() for q in result.mains_questions],
                model=settings.anthropic_model,
            )
        )

    stats.enriched += 1
    logger.info(
        "Enriched article id=%s upsc_relevance=%s relevant=%s title=%r",
        article["id"],
        result.upsc_relevance,
        upsc_relevant,
        article["title"][:60],
    )


def run_enrich(*, session_scope: SessionScopeFn = default_session_scope) -> EnrichStats:
    """Enrich every article that doesn't yet have an Enrichment row.

    Idempotent: safe to call repeatedly (e.g. on a schedule) since pending
    articles are selected by a left join against the Enrichment table.
    """
    settings = get_settings()
    stats = EnrichStats()

    with session_scope() as session:
        pending = _load_pending_articles(session)
    stats.pending = len(pending)

    for index, article in enumerate(pending):
        if index > 0:
            time.sleep(settings.anthropic_request_delay_seconds)
        try:
            _enrich_one(article, session_scope, stats)
        except EnrichmentBlockedError as exc:
            # Every remaining article would fail the same way, so stop instead
            # of spending the rest of the backlog on calls that cannot succeed.
            stats.blocked = str(exc)
            stats.failed += 1
            stats.failed_article_ids.append(article["id"])
            logger.error(
                "Enrichment blocked after %s of %s articles: %s",
                index + 1,
                stats.pending,
                exc,
            )
            break

    logger.info(
        "Enrichment complete: pending=%s enriched=%s failed=%s%s",
        stats.pending,
        stats.enriched,
        stats.failed,
        f" blocked={stats.blocked}" if stats.blocked else "",
    )
    return stats
