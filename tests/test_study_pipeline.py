from contextlib import contextmanager
from datetime import datetime

import pytest

from pib_agent.db.models import Article, Enrichment, Ministry
from pib_agent.study.client import StudyError
from pib_agent.study.pipeline import run_study
from pib_agent.study.schema import MainsPoint, PrelimsPoint, StudyNotes


def _notes(classification: str = "PRELIMS") -> StudyNotes:
    return StudyNotes(
        classification=classification,
        reason="Testable institutional detail.",
        prelims=[
            PrelimsPoint(
                point="Scheme sits under the named ministry.",
                importance="IMPORTANT",
                syllabus="Government Schemes",
                why_important="Agency pairings are standard statement-matching material.",
            )
        ],
        mains=[
            MainsPoint(
                point="Implementation capacity is the binding constraint.",
                importance="WORTH_A_LOOK",
                gs_paper="GS2",
                theme="Governance",
                analytical_use="Supports questions on delivery gaps.",
            )
        ],
    )


def _make_article(session, prid: int, ministry: Ministry, title: str = "Title") -> Article:
    article = Article(
        prid=prid,
        ministry=ministry,
        title=title,
        subtitle=None,
        body_text="Body text.",
        body_html="<p>Body text.</p>",
        pib_office="PIB Delhi",
        release_datetime=datetime(2026, 8, 19, 12, 0),
        source_url=f"https://pib.gov.in/x?PRID={prid}",
    )
    session.add(article)
    session.flush()
    return article


def _make_enrichment(session, article: Article, upsc_relevance: int | None) -> Enrichment:
    enrichment = Enrichment(
        article_id=article.id,
        summary="Summary.",
        context="Context.",
        upsc_relevance=upsc_relevance,
        upsc_relevant=bool(upsc_relevance and upsc_relevance >= 3),
        syllabus_topics=["GS Paper 2 - Governance"],
        prelims_questions=[],
        mains_questions=[],
        model="claude-sonnet-5",
    )
    session.add(enrichment)
    session.flush()
    return enrichment


@pytest.fixture()
def scope_factory(db_session):
    @contextmanager
    def _scope():
        yield db_session
        db_session.flush()

    return _scope


@pytest.fixture()
def ministry(db_session) -> Ministry:
    m = Ministry(name="Ministry of Governance", slug="ministry-of-governance")
    db_session.add(m)
    db_session.flush()
    return m


def test_analyses_articles_above_the_gate(monkeypatch, db_session, scope_factory, ministry):
    article = _make_article(db_session, 1, ministry)
    _make_enrichment(db_session, article, upsc_relevance=4)
    monkeypatch.setattr("pib_agent.study.pipeline.analyse_article", lambda **_: _notes("BOTH"))

    stats = run_study(session_scope=scope_factory)

    assert (stats.pending, stats.analysed, stats.failed) == (1, 1, 0)
    stored = db_session.query(Enrichment).one()
    assert stored.study_classification == "BOTH"
    assert stored.study_notes["prelims"][0]["importance"] == "IMPORTANT"


def test_skips_articles_below_the_gate(monkeypatch, db_session, scope_factory, ministry):
    """The cheap article-level score is what makes the expensive pass affordable."""
    for prid, score in ((1, 1), (2, 2)):
        article = _make_article(db_session, prid, ministry)
        _make_enrichment(db_session, article, upsc_relevance=score)
    called = []
    monkeypatch.setattr(
        "pib_agent.study.pipeline.analyse_article",
        lambda **kw: called.append(kw) or _notes(),
    )

    stats = run_study(session_scope=scope_factory)

    assert stats.pending == 0
    assert called == []


def test_skips_rows_with_no_relevance_score(monkeypatch, db_session, scope_factory, ministry):
    """Rows enriched before the graded score exist in bulk and hold NULL.

    A NULL comparison is false in SQL, so they fall out of the gate rather
    than being silently treated as zero or as passing.
    """
    article = _make_article(db_session, 1, ministry)
    _make_enrichment(db_session, article, upsc_relevance=None)
    monkeypatch.setattr("pib_agent.study.pipeline.analyse_article", lambda **_: _notes())

    stats = run_study(session_scope=scope_factory)

    assert stats.pending == 0


def test_one_failure_does_not_abort_the_batch(monkeypatch, db_session, scope_factory, ministry):
    good = _make_article(db_session, 1, ministry, title="Good")
    bad = _make_article(db_session, 2, ministry, title="Bad")
    _make_enrichment(db_session, good, upsc_relevance=4)
    _make_enrichment(db_session, bad, upsc_relevance=4)

    def flaky(**kwargs):
        if kwargs["title"] == "Bad":
            raise StudyError("model blew up")
        return _notes()

    monkeypatch.setattr("pib_agent.study.pipeline.analyse_article", flaky)

    stats = run_study(session_scope=scope_factory)

    assert (stats.analysed, stats.failed) == (1, 1)
    assert stats.failed_article_ids == [bad.id]
    by_article = {e.article_id: e for e in db_session.query(Enrichment).all()}
    assert by_article[good.id].study_notes is not None
    assert by_article[bad.id].study_notes is None


def test_is_idempotent(monkeypatch, db_session, scope_factory, ministry):
    article = _make_article(db_session, 1, ministry)
    _make_enrichment(db_session, article, upsc_relevance=5)
    calls = []
    monkeypatch.setattr(
        "pib_agent.study.pipeline.analyse_article",
        lambda **kw: calls.append(kw) or _notes(),
    )

    run_study(session_scope=scope_factory)
    second = run_study(session_scope=scope_factory)

    # Already-analysed rows are excluded by `study_notes IS NULL`, so a repeat
    # run (scheduled, or resuming a partial backfill) costs nothing.
    assert len(calls) == 1
    assert second.pending == 0


def test_disabled_flag_skips_everything(monkeypatch, db_session, scope_factory, ministry):
    article = _make_article(db_session, 1, ministry)
    _make_enrichment(db_session, article, upsc_relevance=5)
    monkeypatch.setenv("STUDY_NOTES_ENABLED", "false")
    from pib_agent.config import get_settings

    get_settings.cache_clear()
    called = []
    monkeypatch.setattr(
        "pib_agent.study.pipeline.analyse_article",
        lambda **kw: called.append(kw) or _notes(),
    )

    try:
        stats = run_study(session_scope=scope_factory)
    finally:
        get_settings.cache_clear()

    assert stats.pending == 0
    assert called == []
