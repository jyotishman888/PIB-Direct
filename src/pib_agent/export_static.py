"""Export the corpus as a static JSON bundle for hosting without a backend.

GitHub Pages serves files, not Python, so the deployed site reads pre-built
JSON instead of calling the API. The payload shapes come from
``pib_agent.api.mapping`` rather than being written by hand here, which is the
whole point of reusing them: the emitted JSON matches the live API contract
exactly, so the frontend's TypeScript types cover both sources.

Only the public corpus is read — articles, enrichments, ministries and links.
The ``users``, ``auth_identities``, ``user_sessions`` and ``subscriptions``
tables are never touched, because this bundle is committed to a public
repository and those tables hold real email addresses, provider subject ids
and session token hashes.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from pib_agent.api.mapping import to_article_detail, to_article_list_item
from pib_agent.api.schemas import MinistryListItem, TopicListItem
from pib_agent.db.models import Article, ArticleLink, Enrichment, Ministry
from pib_agent.syllabus import GS_AREAS, area_slug

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 30
DEFAULT_EXPORT_DIR = Path("frontend/public/data")


@dataclass(frozen=True)
class ExportResult:
    out_dir: Path
    article_count: int
    ministry_count: int
    latest_date: str | None
    window_days: int


def _write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _cutoff_for(session: Session, days: int) -> datetime | None:
    """Window back from the newest release, not from today.

    Anchoring on ``now`` would silently produce an empty bundle whenever the
    scraper has been down for longer than the window — the export would look
    like it succeeded while publishing nothing.
    """
    newest = (
        session.query(Article.release_datetime)
        .filter(Article.release_datetime.isnot(None))
        .order_by(Article.release_datetime.desc())
        .first()
    )
    if newest is None or newest[0] is None:
        return None
    return datetime.combine((newest[0] - timedelta(days=days - 1)).date(), time.min)


def export_static(out_dir: Path, session: Session, days: int = DEFAULT_WINDOW_DAYS) -> ExportResult:
    """Write the JSON bundle to ``out_dir``, replacing anything already there."""
    if days < 1:
        raise ValueError("days must be at least 1")

    out_dir = Path(out_dir)
    if out_dir.exists():
        # Rebuild from scratch so articles that fall out of the window stop
        # being served; otherwise stale detail files accumulate forever.
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cutoff = _cutoff_for(session, days)

    query = session.query(Article).join(Ministry).outerjoin(Enrichment)
    if cutoff is not None:
        query = query.filter(Article.release_datetime >= cutoff)
    articles = query.order_by(Article.release_datetime.desc(), Article.id.desc()).all()

    # index.json — every article in the window, in the same shape and default
    # order the list endpoint returns.
    items = [to_article_list_item(article) for article in articles]
    _write_json(
        out_dir / "index.json",
        json.dumps([json.loads(item.model_dump_json()) for item in items], ensure_ascii=False),
    )

    # One detail file per article, matching GET /api/articles/{id}.
    links_by_article: dict[int, list[ArticleLink]] = {}
    if articles:
        ids = [article.id for article in articles]
        for link in (
            session.query(ArticleLink)
            .filter(ArticleLink.article_id.in_(ids))
            .order_by(ArticleLink.id)
            .all()
        ):
            links_by_article.setdefault(link.article_id, []).append(link)

    for article in articles:
        detail = to_article_detail(article, links_by_article.get(article.id, []))
        _write_json(out_dir / "articles" / f"{article.id}.json", detail.model_dump_json())

    # Ministry counts are recomputed over the window rather than copied from
    # the live endpoint, which counts the whole corpus — otherwise the sidebar
    # advertises releases that aren't in this bundle.
    counts: dict[int, int] = {}
    for article in articles:
        counts[article.ministry_id] = counts.get(article.ministry_id, 0) + 1

    ministries = [
        MinistryListItem(
            id=ministry.id,
            name=ministry.name,
            slug=ministry.slug,
            article_count=counts.get(ministry.id, 0),
        )
        for ministry in session.query(Ministry).order_by(Ministry.name).all()
        if counts.get(ministry.id, 0) > 0
    ]
    _write_json(
        out_dir / "ministries.json",
        json.dumps([json.loads(m.model_dump_json()) for m in ministries], ensure_ascii=False),
    )

    # topics.json is a separate file for the same reason ministries.json is:
    # the sidebar renders on first paint, and deriving topics from index.json
    # would force the whole index to load on the digest, which avoids it today.
    topic_counts: dict[str, int] = {}
    for article in articles:
        for tag in (article.enrichment.syllabus_topics if article.enrichment else []) or []:
            topic_counts[tag] = topic_counts.get(tag, 0) + 1
    topics = [
        TopicListItem(name=area, slug=area_slug(area), article_count=topic_counts[area])
        for area in GS_AREAS
        if topic_counts.get(area)
    ]
    _write_json(
        out_dir / "topics.json",
        json.dumps([json.loads(t.model_dump_json()) for t in topics], ensure_ascii=False),
    )

    # The digest keys off latest_date rather than the visitor's clock: a
    # snapshot built days ago would otherwise land every visitor on the
    # "nothing published yet today" empty state.
    dated = [a.release_datetime for a in articles if a.release_datetime is not None]
    latest_date: str | None = max(dated).date().isoformat() if dated else None

    _write_json(
        out_dir / "meta.json",
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "latest_date": latest_date,
                "article_count": len(articles),
                "ministry_count": len(ministries),
                "topic_count": len(topics),
                "window_days": days,
            },
            ensure_ascii=False,
        ),
    )

    logger.info(
        "Exported %d articles across %d ministries to %s",
        len(articles),
        len(ministries),
        out_dir,
    )
    return ExportResult(
        out_dir=out_dir,
        article_count=len(articles),
        ministry_count=len(ministries),
        latest_date=latest_date,
        window_days=days,
    )
