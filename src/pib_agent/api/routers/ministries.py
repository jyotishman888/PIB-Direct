from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from pib_agent.api.deps import get_db
from pib_agent.api.schemas import MinistryListItem
from pib_agent.db.models import Article, Ministry

router = APIRouter(prefix="/ministries", tags=["ministries"])


@router.get("", response_model=list[MinistryListItem])
def list_ministries(session: Session = Depends(get_db)) -> list[MinistryListItem]:
    rows = (
        session.query(Ministry, func.count(Article.id))
        .outerjoin(Article, Article.ministry_id == Ministry.id)
        .group_by(Ministry.id)
        .order_by(Ministry.name)
        .all()
    )
    return [
        MinistryListItem(
            id=ministry.id, name=ministry.name, slug=ministry.slug, article_count=count
        )
        for ministry, count in rows
    ]
