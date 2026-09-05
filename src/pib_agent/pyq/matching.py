"""Find the past-year questions that share an article's syllabus areas.

This is a join, not a similarity search, and that is the whole payoff of
pinning both sides to the closed vocabulary in syllabus.py: an article tagged
"GS Paper 2 - Federalism" and a 2019 mains question tagged the same way match
exactly, with nothing to tune and nothing to get subtly wrong.

What it buys the reader is evidence rather than assertion. "Worth studying"
is an opinion; "this area was examined in 2023, 2021 and 2019" is a fact they
can act on.
"""

import logging
from collections import Counter

from sqlalchemy.orm import Session

from pib_agent.db.models import PastQuestion

logger = logging.getLogger(__name__)

# An article carries at most two areas (enrichment/client.py caps it), and a
# heavily-examined area like Economy can hold far more questions than a narrow
# one. Capping per area rather than overall keeps the second area visible
# instead of letting the first crowd it out.
MAX_PER_AREA = 3


def find_past_questions(session: Session, areas: list[str]) -> list[PastQuestion]:
    """Past questions sharing any of ``areas``, newest first, capped per area.

    Returns [] when the article has no areas or the corpus is empty, which is
    the normal state until an operator imports real questions — nothing in
    this project invents them.
    """
    if not areas:
        return []

    rows = (
        session.query(PastQuestion)
        .filter(PastQuestion.syllabus_area.in_(areas))
        .order_by(
            PastQuestion.syllabus_area,
            PastQuestion.year.desc(),
            PastQuestion.id,
        )
        .all()
    )

    kept: list[PastQuestion] = []
    per_area: Counter[str] = Counter()
    for row in rows:
        area = row.syllabus_area or ""
        if per_area[area] >= MAX_PER_AREA:
            continue
        per_area[area] += 1
        kept.append(row)

    # Newest first across the whole set, so the most recent evidence leads
    # regardless of which area it came from.
    kept.sort(key=lambda r: (-r.year, r.syllabus_area or "", r.id))
    return kept
