import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import TypedDict

from sqlalchemy.orm import Session

from pib_agent.config import get_settings
from pib_agent.db import Article, Enrichment
from pib_agent.db import session_scope as default_session_scope
from pib_agent.study.client import StudyError, analyse_article

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


class _PendingArticle(TypedDict):
    enrichment_id: int
    article_id: int
    title: str
    ministry_name: str
    summary: str
    context: str
    syllabus_topics: list[str]
    body_text: str
    upsc_relevance: int


@dataclass
class StudyStats:
    pending: int = 0
    analysed: int = 0
    failed: int = 0
    failed_article_ids: list[int] = field(default_factory=list)


def _load_pending(session: Session, min_relevance: int) -> list[_PendingArticle]:
    """Enriched articles that cleared the relevance gate and have no notes yet.

    The gate is the point of the two-tier design: the cheap article-level score
    from enrichment decides whether the expensive point-level extraction is
    worth running at all. Rows predating that score hold NULL and are skipped —
    a NULL comparison is false in SQL, so they fall out naturally.
    """
    rows = (
        session.query(Enrichment)
        .join(Article, Article.id == Enrichment.article_id)
        .filter(Enrichment.study_notes.is_(None))
        .filter(Enrichment.upsc_relevance >= min_relevance)
        .order_by(Enrichment.upsc_relevance.desc(), Enrichment.article_id.desc())
        .all()
    )
    return [
        {
            "enrichment_id": e.id,
            "article_id": e.article_id,
            "title": e.article.title,
            "ministry_name": e.article.ministry.name,
            "summary": e.summary,
            "context": e.context,
            "syllabus_topics": e.syllabus_topics or [],
            "body_text": e.article.body_text,
            "upsc_relevance": e.upsc_relevance,
        }
        for e in rows
    ]


def _analyse_one(
    pending: _PendingArticle, session_scope: SessionScopeFn, stats: StudyStats
) -> None:
    try:
        notes = analyse_article(
            title=pending["title"],
            ministry_name=pending["ministry_name"],
            summary=pending["summary"],
            context=pending["context"],
            syllabus_topics=pending["syllabus_topics"],
            body_text=pending["body_text"],
            upsc_relevance=pending["upsc_relevance"],
        )
    except StudyError as exc:
        # Isolated per article: one bad release must not abort the batch.
        logger.error("Failed to analyse article id=%s: %s", pending["article_id"], exc)
        stats.failed += 1
        stats.failed_article_ids.append(pending["article_id"])
        return

    with session_scope() as session:
        enrichment = session.get(Enrichment, pending["enrichment_id"])
        if enrichment is None or enrichment.study_notes is not None:
            # Row vanished, or a concurrent run got there first.
            return
        enrichment.study_notes = notes.model_dump()
        enrichment.study_classification = notes.classification

    stats.analysed += 1
    logger.info(
        "Analysed article id=%s classification=%s prelims=%d mains=%d both=%d title=%r",
        pending["article_id"],
        notes.classification,
        len(notes.prelims),
        len(notes.mains),
        len(notes.both),
        pending["title"][:60],
    )


def run_study(*, session_scope: SessionScopeFn = default_session_scope) -> StudyStats:
    """Extract UPSC study notes for enriched articles above the relevance gate.

    Idempotent: pending rows are selected by `study_notes IS NULL`, so repeated
    runs (on a schedule, or resuming a partial backfill) only pick up what is
    genuinely outstanding.
    """
    settings = get_settings()
    stats = StudyStats()

    if not settings.study_notes_enabled:
        logger.info("Study pass disabled (STUDY_NOTES_ENABLED=false); skipping.")
        return stats

    with session_scope() as session:
        pending = _load_pending(session, settings.study_notes_min_relevance)
    stats.pending = len(pending)

    for index, item in enumerate(pending):
        if index > 0:
            time.sleep(settings.anthropic_request_delay_seconds)
        _analyse_one(item, session_scope, stats)

    logger.info(
        "Study pass complete: pending=%s analysed=%s failed=%s",
        stats.pending,
        stats.analysed,
        stats.failed,
    )
    return stats
