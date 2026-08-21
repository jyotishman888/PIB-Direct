import json
from contextlib import contextmanager

import pytest

from pib_agent.db.models import PastQuestion
from pib_agent.pyq import PyqImportError, import_past_questions


@pytest.fixture()
def scope_factory(db_session):
    @contextmanager
    def _scope():
        yield db_session
        db_session.flush()

    return _scope


def _write(tmp_path, rows, name="pyq.json"):
    path = tmp_path / name
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


ROWS = [
    {
        "year": 2019,
        "paper": "prelims",
        "question": "Consider the following statements about the Ramsar Convention:",
        "syllabus_area": "GS Paper 3 - Environment and Biodiversity",
    },
    {
        "year": 2022,
        "paper": "mains",
        "question": "Discuss the challenges of semiconductor self-reliance in India.",
        "topic": "Science & Technology",
    },
]


def test_imports_rows(tmp_path, db_session, scope_factory):
    stats = import_past_questions(_write(tmp_path, ROWS), session_scope=scope_factory)

    assert (stats.read, stats.imported, stats.rejected) == (2, 2, 0)
    stored = db_session.query(PastQuestion).order_by(PastQuestion.year).all()
    assert stored[0].year == 2019
    assert stored[0].syllabus_area == "GS Paper 3 - Environment and Biodiversity"


def test_source_topic_is_normalised_onto_the_shared_vocabulary(tmp_path, db_session, scope_factory):
    """Matching articles to questions is only a join if both sides use the
    same taxonomy — 'Science & Technology' and the canonical area are one."""
    import_past_questions(_write(tmp_path, ROWS), session_scope=scope_factory)

    mains = db_session.query(PastQuestion).filter_by(paper="mains").one()
    assert mains.syllabus_area == "GS Paper 3 - Science and Technology"
    # the source's own wording survives for traceability
    assert mains.source_topic == "Science & Technology"


def test_unmappable_area_is_stored_as_null_not_guessed(tmp_path, db_session, scope_factory):
    """A wrong area is worse than none: it would surface an unrelated question
    against an article."""
    rows = [{"year": 2020, "paper": "prelims", "question": "Q.", "syllabus_area": "Zzqq Wibble"}]

    stats = import_past_questions(_write(tmp_path, rows), session_scope=scope_factory)

    assert stats.imported == 1
    assert stats.unmapped_area == 1
    assert db_session.query(PastQuestion).one().syllabus_area is None


def test_reimport_is_idempotent(tmp_path, db_session, scope_factory):
    path = _write(tmp_path, ROWS)
    import_past_questions(path, session_scope=scope_factory)

    second = import_past_questions(path, session_scope=scope_factory)

    assert (second.imported, second.duplicates) == (0, 2)
    assert db_session.query(PastQuestion).count() == 2


def test_duplicates_within_one_file_are_collapsed(tmp_path, db_session, scope_factory):
    rows = ROWS + [dict(ROWS[0])]

    stats = import_past_questions(_write(tmp_path, rows), session_scope=scope_factory)

    assert (stats.imported, stats.duplicates) == (2, 1)


@pytest.mark.parametrize(
    "row",
    [
        {"year": 2019, "paper": "prelims"},  # no question
        {"year": "not-a-year", "paper": "prelims", "question": "Q."},
        {"year": 2019, "paper": "essay", "question": "Q."},  # unknown paper
    ],
)
def test_bad_rows_are_rejected_with_a_reason(tmp_path, db_session, scope_factory, row):
    stats = import_past_questions(_write(tmp_path, [row]), session_scope=scope_factory)

    assert stats.imported == 0
    assert stats.rejected == 1
    assert stats.errors
    assert db_session.query(PastQuestion).count() == 0


def test_one_bad_row_does_not_lose_the_good_ones(tmp_path, db_session, scope_factory):
    rows = [*ROWS, {"year": 2021, "paper": "prelims"}]

    stats = import_past_questions(_write(tmp_path, rows), session_scope=scope_factory)

    assert (stats.imported, stats.rejected) == (2, 1)


def test_source_is_recorded_so_a_bad_batch_can_be_found(tmp_path, db_session, scope_factory):
    import_past_questions(
        _write(tmp_path, ROWS), source="upsc-2019-2022.json", session_scope=scope_factory
    )

    assert {q.source for q in db_session.query(PastQuestion).all()} == {"upsc-2019-2022.json"}


def test_csv_is_accepted(tmp_path, db_session, scope_factory):
    path = tmp_path / "pyq.csv"
    path.write_text(
        "year,paper,question,syllabus_area\n"
        "2018,prelims,What is the Ramsar Convention?,GS Paper 3 - Environment and Biodiversity\n",
        encoding="utf-8",
    )

    stats = import_past_questions(path, session_scope=scope_factory)

    assert stats.imported == 1
    assert db_session.query(PastQuestion).one().year == 2018


def test_missing_file_and_bad_json_are_reported_clearly(tmp_path, scope_factory):
    with pytest.raises(PyqImportError, match="No such file"):
        import_past_questions(tmp_path / "nope.json", session_scope=scope_factory)

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(PyqImportError, match="not valid JSON"):
        import_past_questions(bad, session_scope=scope_factory)


def test_unsupported_extension_is_rejected(tmp_path, scope_factory):
    path = tmp_path / "pyq.txt"
    path.write_text("whatever", encoding="utf-8")

    with pytest.raises(PyqImportError, match="Unsupported file type"):
        import_past_questions(path, session_scope=scope_factory)
