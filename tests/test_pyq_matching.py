"""Matching is a join on the shared vocabulary, not a similarity search."""

from pib_agent.db.models import PastQuestion
from pib_agent.pyq.matching import MAX_PER_AREA, find_past_questions

FEDERALISM = "GS Paper 2 - Federalism"
ECONOMY = "GS Paper 3 - Economy"


def _seed(session, rows):
    for year, paper, question, area in rows:
        session.add(
            PastQuestion(
                year=year, paper=paper, question=question, syllabus_area=area, source="test"
            )
        )
    session.flush()


def test_returns_only_questions_sharing_an_area(db_session):
    _seed(
        db_session,
        [
            (2019, "mains", "Finance Commission and fiscal balance?", FEDERALISM),
            (2021, "mains", "GST and state finances?", ECONOMY),
            (2020, "mains", "Monsoon variability?", "GS Paper 1 - Geography"),
        ],
    )

    found = find_past_questions(db_session, [FEDERALISM, ECONOMY])

    assert {q.syllabus_area for q in found} == {FEDERALISM, ECONOMY}
    assert all("Monsoon" not in q.question for q in found)


def test_newest_first(db_session):
    _seed(
        db_session,
        [
            (2015, "mains", "old", FEDERALISM),
            (2023, "mains", "recent", FEDERALISM),
            (2019, "mains", "middling", FEDERALISM),
        ],
    )

    assert [q.year for q in find_past_questions(db_session, [FEDERALISM])] == [2023, 2019, 2015]


def test_a_crowded_area_cannot_squeeze_out_the_other(db_session):
    """Economy holds far more questions than a narrow area; both must show."""
    _seed(
        db_session,
        [(2000 + i, "mains", f"economy q{i}", ECONOMY) for i in range(1, 11)]
        + [(1999, "mains", "the only federalism question", FEDERALISM)],
    )

    found = find_past_questions(db_session, [ECONOMY, FEDERALISM])

    assert len(found) == MAX_PER_AREA + 1
    assert FEDERALISM in {q.syllabus_area for q in found}


def test_empty_corpus_and_untagged_article_return_nothing(db_session):
    assert find_past_questions(db_session, [FEDERALISM]) == []
    _seed(db_session, [(2019, "mains", "q", FEDERALISM)])
    assert find_past_questions(db_session, []) == []
