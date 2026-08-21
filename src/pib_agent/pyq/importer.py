"""Import real past-year UPSC questions from an operator-supplied file.

Nothing in this project generates these. A fabricated "this was asked in 2019"
is the fastest way to lose an exam aspirant's trust, so the corpus is fed only
by import, and every row records the `source` it came from — which is also what
makes a bad batch identifiable and removable later.

Accepts JSON (a list of objects) or CSV with the same field names:

    year          required, integer
    paper         required, "prelims" or "mains"
    question      required, the question text
    syllabus_area optional, a canonical GS area; free text is normalised, and
                  anything unmappable is stored as NULL rather than guessed
    topic         optional, the source's own topic label, kept verbatim
"""

from __future__ import annotations

import csv
import json
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pib_agent.db import session_scope as default_session_scope
from pib_agent.db.models import PastQuestion
from pib_agent.syllabus import normalise_area

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]

VALID_PAPERS = {"prelims", "mains"}


class PyqImportError(RuntimeError):
    """Raised when the source file cannot be read or is structurally wrong."""


@dataclass
class ImportStats:
    read: int = 0
    imported: int = 0
    duplicates: int = 0
    unmapped_area: int = 0
    rejected: int = 0
    errors: list[str] = field(default_factory=list)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise PyqImportError(f"No such file: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PyqImportError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise PyqImportError(f"{path} must contain a list of objects.")
        return data
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(text.splitlines()))
    raise PyqImportError(f"Unsupported file type {path.suffix!r}; use .json or .csv.")


def _clean(row: dict[str, Any], stats: ImportStats) -> PastQuestion | None:
    """Validate one row, or record why it was rejected and return None."""
    question = str(row.get("question") or "").strip()
    if not question:
        stats.rejected += 1
        stats.errors.append("row missing 'question'")
        return None

    raw_year = row.get("year")
    try:
        year = int(str(raw_year).strip())
    except (TypeError, ValueError):
        stats.rejected += 1
        stats.errors.append(f"row has non-numeric year {raw_year!r}: {question[:40]}")
        return None

    paper = str(row.get("paper") or "").strip().lower()
    if paper not in VALID_PAPERS:
        stats.rejected += 1
        stats.errors.append(f"row has paper {paper!r}, expected one of {sorted(VALID_PAPERS)}")
        return None

    source_topic = (str(row.get("topic")).strip() or None) if row.get("topic") else None

    # Pinned to the same vocabulary the articles use — that shared taxonomy is
    # the whole point, since it turns matching into a join rather than fuzzy
    # text overlap. Unmappable values become NULL; a wrong area is worse than
    # no area, because it would surface an unrelated question on an article.
    raw_area = row.get("syllabus_area") or source_topic
    area = normalise_area(str(raw_area)) if raw_area else None
    if raw_area and area is None:
        stats.unmapped_area += 1

    return PastQuestion(
        year=year,
        paper=paper,
        question=question,
        syllabus_area=area,
        source_topic=source_topic,
        source="",  # set by the caller, which knows the file
    )


def import_past_questions(
    path: Path,
    *,
    source: str | None = None,
    session_scope: SessionScopeFn = default_session_scope,
) -> ImportStats:
    """Load questions from ``path``. Idempotent: re-importing changes nothing.

    Duplicates are detected on (year, paper, question), so the same file can be
    re-run after a partial failure without doubling the corpus.
    """
    path = Path(path)
    rows: Iterable[dict[str, Any]] = _load_rows(path)
    stats = ImportStats()
    label = source or path.name

    with session_scope() as session:
        existing = {
            (year, paper, question)
            for year, paper, question in session.query(
                PastQuestion.year, PastQuestion.paper, PastQuestion.question
            ).all()
        }
        seen_in_file: set[tuple[int, str, str]] = set()

        for row in rows:
            stats.read += 1
            question = _clean(row, stats)
            if question is None:
                continue

            key = (question.year, question.paper, question.question)
            if key in existing or key in seen_in_file:
                stats.duplicates += 1
                continue

            question.source = label
            seen_in_file.add(key)
            session.add(question)
            stats.imported += 1

    logger.info(
        "PYQ import from %s: read=%d imported=%d duplicates=%d rejected=%d unmapped_area=%d",
        label,
        stats.read,
        stats.imported,
        stats.duplicates,
        stats.rejected,
        stats.unmapped_area,
    )
    return stats
