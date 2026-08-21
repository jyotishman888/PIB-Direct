from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, nullslast
from sqlalchemy.orm import Session

from pib_agent.api.deps import get_db
from pib_agent.api.mapping import to_article_detail, to_article_list_item
from pib_agent.api.schemas import ArticleDetail, PaginatedArticles
from pib_agent.db.models import Article, ArticleLink, Enrichment, Ministry
from pib_agent.syllabus import area_from_slug

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=PaginatedArticles)
def list_articles(
    session: Session = Depends(get_db),
    ministry: str | None = Query(None, description="Filter by ministry slug"),
    topic: str | None = Query(None, description="Filter by syllabus area slug"),
    upsc_relevant: bool | None = Query(None, description="Filter by UPSC relevance"),
    search: str | None = Query(None, min_length=2, description="Matches title or summary"),
    date_from: date | None = Query(None, description="Only releases on/after this date"),
    date_to: date | None = Query(None, description="Only releases on/before this date"),
    sort: Literal["newest", "relevance"] = Query(
        "newest", description="'relevance' ranks by UPSC study-worthiness score first"
    ),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedArticles:
    query = session.query(Article).join(Ministry).outerjoin(Enrichment)

    if ministry is not None:
        query = query.filter(Ministry.slug == ministry)
    if topic is not None:
        area = area_from_slug(topic)
        if area is None:
            # An unrecognised slug matches nothing rather than 404ing: a stale
            # bookmark should land on an empty list, not an error page.
            return PaginatedArticles(items=[], total=0, limit=limit, offset=offset)
        # Matched against the serialised JSON so this works on SQLite and
        # Postgres alike. Exact despite being a LIKE: the quotes bound the
        # match, and the vocabulary is plain ASCII with nothing JSON escapes.
        query = query.filter(cast(Enrichment.syllabus_topics, String).like(f'%"{area}"%'))
    if upsc_relevant is not None:
        query = query.filter(Enrichment.upsc_relevant == upsc_relevant)
    if search is not None:
        like = f"%{search}%"
        query = query.filter(Article.title.ilike(like) | Enrichment.summary.ilike(like))
    if date_from is not None:
        query = query.filter(Article.release_datetime >= datetime.combine(date_from, time.min))
    if date_to is not None:
        query = query.filter(Article.release_datetime <= datetime.combine(date_to, time.max))

    total = query.count()
    if sort == "relevance":
        # The digest's whole premise: rank by study-worthiness first, so the
        # handful of releases that matter surface even on a heavy day,
        # regardless of where they'd fall in a pure date ordering.
        order = (
            nullslast(Enrichment.upsc_relevance.desc()),
            nullslast(Article.release_datetime.desc()),
            Article.id.desc(),
        )
    else:
        order = (nullslast(Article.release_datetime.desc()), Article.id.desc())

    rows = query.order_by(*order).offset(offset).limit(limit).all()

    return PaginatedArticles(
        items=[to_article_list_item(article) for article in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{article_id}", response_model=ArticleDetail)
def get_article(article_id: int, session: Session = Depends(get_db)) -> ArticleDetail:
    article = session.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")

    links = (
        session.query(ArticleLink)
        .filter(ArticleLink.article_id == article_id)
        .order_by(ArticleLink.id)
        .all()
    )
    return to_article_detail(article, links)
