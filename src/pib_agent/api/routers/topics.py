from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pib_agent.api.deps import get_db
from pib_agent.api.schemas import TopicListItem
from pib_agent.db.models import Enrichment
from pib_agent.syllabus import GS_AREAS, area_slug

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[TopicListItem])
def list_topics(session: Session = Depends(get_db)) -> list[TopicListItem]:
    """Canonical syllabus areas that have at least one article.

    Counted in Python rather than SQL because the tags live in a JSON array
    and the vocabulary is 32 fixed strings — a single scan of the column beats
    32 dialect-specific LIKE counts, and keeps this working on SQLite and
    Postgres alike.

    Only canonical areas appear. A residue of legacy free-text tags survives on
    older rows where normalise_area could not map them confidently; listing
    those would rebuild the one-off sprawl this vocabulary exists to prevent.
    Their articles stay reachable by ministry, search and date.
    """
    counts: dict[str, int] = {}
    for (tags,) in session.query(Enrichment.syllabus_topics).all():
        for tag in tags or []:
            counts[tag] = counts.get(tag, 0) + 1

    return [
        TopicListItem(name=area, slug=area_slug(area), article_count=counts[area])
        for area in GS_AREAS
        if counts.get(area)
    ]
