import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TypedDict

import numpy as np
from sqlalchemy.orm import Session

from pib_agent.config import get_settings
from pib_agent.db import Article, ArticleLink, Embedding, Enrichment
from pib_agent.db import session_scope as default_session_scope
from pib_agent.similarity.client import SimilarityError, find_related_links
from pib_agent.similarity.embeddings import embed_text
from pib_agent.similarity.prompts import Candidate
from pib_agent.similarity.vectors import bytes_to_vector, vector_to_bytes

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]


class _PendingEmbed(TypedDict):
    article_id: int
    title: str
    summary: str


class _PendingLink(TypedDict):
    embedding_id: int
    article_id: int
    title: str
    ministry_name: str
    summary: str
    release_datetime: datetime | None
    vector: np.ndarray


class _CandidateRow(TypedDict):
    article_id: int
    title: str
    ministry_name: str
    summary: str
    release_datetime: datetime | None
    vector: np.ndarray


@dataclass
class SimilarityStats:
    embed_pending: int = 0
    embedded: int = 0
    embed_failed: int = 0
    link_pending: int = 0
    linked: int = 0
    links_created: int = 0
    link_failed: int = 0
    link_failed_article_ids: list[int] = field(default_factory=list)


def _load_pending_embeds(session: Session) -> list[_PendingEmbed]:
    rows = (
        session.query(Article)
        .join(Enrichment, Enrichment.article_id == Article.id)
        .outerjoin(Embedding, Embedding.article_id == Article.id)
        .filter(Embedding.id.is_(None))
        .order_by(Article.id)
        .all()
    )
    return [
        {"article_id": a.id, "title": a.title, "summary": a.enrichment.summary} for a in rows
    ]


def _embed_one(
    item: _PendingEmbed, session_scope: SessionScopeFn, stats: SimilarityStats
) -> None:
    settings = get_settings()
    try:
        vector = embed_text(f"{item['title']}\n\n{item['summary']}")
    except Exception:
        logger.exception("Failed to compute embedding for article id=%s", item["article_id"])
        stats.embed_failed += 1
        return

    with session_scope() as session:
        if (
            session.query(Embedding).filter_by(article_id=item["article_id"]).one_or_none()
            is not None
        ):
            return
        session.add(
            Embedding(
                article_id=item["article_id"],
                vector=vector_to_bytes(vector),
                dim=int(vector.shape[0]),
                model=settings.embedding_model,
            )
        )
    stats.embedded += 1


def _load_pending_links(session: Session) -> list[_PendingLink]:
    rows = (
        session.query(Embedding)
        .join(Article, Article.id == Embedding.article_id)
        .filter(Embedding.linked_at.is_(None))
        .order_by(Article.id)
        .all()
    )
    return [
        {
            "embedding_id": e.id,
            "article_id": e.article_id,
            "title": e.article.title,
            "ministry_name": e.article.ministry.name,
            "summary": e.article.enrichment.summary,
            "release_datetime": e.article.release_datetime,
            "vector": bytes_to_vector(e.vector),
        }
        for e in rows
    ]


def _load_candidates(session: Session, before_article_id: int) -> list[_CandidateRow]:
    rows = (
        session.query(Embedding)
        .join(Article, Article.id == Embedding.article_id)
        .filter(Embedding.article_id < before_article_id)
        .all()
    )
    return [
        {
            "article_id": e.article_id,
            "title": e.article.title,
            "ministry_name": e.article.ministry.name,
            "summary": e.article.enrichment.summary,
            "release_datetime": e.article.release_datetime,
            "vector": bytes_to_vector(e.vector),
        }
        for e in rows
    ]


def _top_candidates(
    query_vector: np.ndarray, candidates: list[_CandidateRow], *, top_k: int, threshold: float
) -> list[_CandidateRow]:
    if not candidates:
        return []
    matrix = np.stack([c["vector"] for c in candidates])
    similarities = matrix @ query_vector
    ranked = sorted(
        zip(similarities, candidates, strict=True), key=lambda pair: pair[0], reverse=True
    )
    return [c for score, c in ranked if score >= threshold][:top_k]


def _link_one(
    item: _PendingLink, session_scope: SessionScopeFn, stats: SimilarityStats
) -> None:
    settings = get_settings()

    with session_scope() as session:
        candidate_rows = _load_candidates(session, before_article_id=item["article_id"])

    top = _top_candidates(
        item["vector"],
        candidate_rows,
        top_k=settings.similarity_top_k,
        threshold=settings.similarity_threshold,
    )

    related: list[tuple[_CandidateRow, str]] = []
    used_claude = bool(top)
    if top:
        candidates = [
            Candidate(
                index=i,
                title=c["title"],
                ministry_name=c["ministry_name"],
                summary=c["summary"],
                release_datetime=c["release_datetime"],
            )
            for i, c in enumerate(top)
        ]
        try:
            result = find_related_links(
                title=item["title"],
                ministry_name=item["ministry_name"],
                summary=item["summary"],
                release_datetime=item["release_datetime"],
                candidates=candidates,
            )
        except SimilarityError as exc:
            logger.error(
                "Failed to check similarity for article id=%s: %s", item["article_id"], exc
            )
            stats.link_failed += 1
            stats.link_failed_article_ids.append(item["article_id"])
            return

        for link in result.related_links:
            if not (0 <= link.candidate_index < len(top)):
                logger.warning(
                    "Claude returned out-of-range candidate_index=%s for article id=%s; skipping",
                    link.candidate_index,
                    item["article_id"],
                )
                continue
            related.append((top[link.candidate_index], link.relationship))

    with session_scope() as session:
        embedding_row = session.get(Embedding, item["embedding_id"])
        if embedding_row is None or embedding_row.linked_at is not None:
            return  # deleted or already processed by a concurrent run
        for candidate, note in related:
            exists = (
                session.query(ArticleLink)
                .filter_by(
                    article_id=item["article_id"], related_article_id=candidate["article_id"]
                )
                .one_or_none()
            )
            if exists is None:
                session.add(
                    ArticleLink(
                        article_id=item["article_id"],
                        related_article_id=candidate["article_id"],
                        relationship_note=note,
                    )
                )
        embedding_row.linked_at = datetime.now(UTC)
        embedding_row.linked_model = settings.anthropic_model if used_claude else None

    stats.linked += 1
    stats.links_created += len(related)
    logger.info(
        "Similarity-checked article id=%s: %s related link(s) from %s candidate(s)",
        item["article_id"],
        len(related),
        len(top),
    )


def run_similarity(*, session_scope: SessionScopeFn = default_session_scope) -> SimilarityStats:
    """Embed any un-embedded (but enriched) articles, then link each un-checked
    article to genuinely related past articles.

    Idempotent: safe to call repeatedly (e.g. on a schedule). Embeddings are
    computed once per article; the linking pass is marked done via
    Embedding.linked_at regardless of whether any links were found, so
    already-checked articles are never re-sent to Claude.
    """
    settings = get_settings()
    stats = SimilarityStats()

    with session_scope() as session:
        pending_embeds = _load_pending_embeds(session)
    stats.embed_pending = len(pending_embeds)
    for embed_item in pending_embeds:
        _embed_one(embed_item, session_scope, stats)

    with session_scope() as session:
        pending_links = _load_pending_links(session)
    stats.link_pending = len(pending_links)
    for index, link_item in enumerate(pending_links):
        if index > 0:
            time.sleep(settings.anthropic_request_delay_seconds)
        _link_one(link_item, session_scope, stats)

    logger.info(
        "Similarity pass complete: embedded=%s/%s linked=%s/%s links_created=%s link_failed=%s",
        stats.embedded,
        stats.embed_pending,
        stats.linked,
        stats.link_pending,
        stats.links_created,
        stats.link_failed,
    )
    return stats
