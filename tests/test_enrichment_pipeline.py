from datetime import datetime

import pytest
from pydantic import ValidationError

from pib_agent.db.models import Article, Enrichment, Ministry
from pib_agent.enrichment.client import EnrichmentError
from pib_agent.enrichment.pipeline import run_enrich
from pib_agent.enrichment.schema import ArticleEnrichment, MainsQuestion, PrelimsQuestion


def _make_article(prid: int, ministry: Ministry, title: str = "Title") -> Article:
    return Article(
        prid=prid,
        ministry=ministry,
        title=title,
        subtitle=None,
        body_text="Some body text.",
        body_html="<p>Some body text.</p>",
        pib_office="PIB Delhi",
        release_datetime=datetime(2026, 8, 9, 12, 0),
        source_url=f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}",
    )


def _sample_enrichment(relevant: bool = True, score: int | None = None) -> ArticleEnrichment:
    # Claude now returns a 1-5 study-worthiness score rather than a boolean;
    # default to a clear pass/fail either side of the default threshold of 3.
    if score is None:
        score = 4 if relevant else 1
    return ArticleEnrichment(
        summary="Summary.",
        context="Context.",
        upsc_relevance=score,
        syllabus_topics=["GS Paper 3 - Economy"] if relevant else [],
        prelims_questions=(
            [
                PrelimsQuestion(
                    question="Q?",
                    options=["A", "B", "C", "D"],
                    correct_option_index=0,
                    explanation="Because.",
                )
            ]
            if relevant
            else []
        ),
        mains_questions=(
            [MainsQuestion(question="Discuss.", gs_paper="GS Paper 3")] if relevant else []
        ),
    )


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("pib_agent.enrichment.pipeline.time.sleep", lambda _seconds: None)


def test_run_enrich_persists_enrichment_for_all_pending(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        session.add_all([_make_article(1, ministry), _make_article(2, ministry)])

    monkeypatch.setattr(
        "pib_agent.enrichment.pipeline.enrich_article", lambda **kwargs: _sample_enrichment()
    )

    stats = run_enrich(session_scope=session_scope_factory)

    assert stats.pending == 2
    assert stats.enriched == 2
    assert stats.failed == 0

    with session_scope_factory() as session:
        enrichments = session.query(Enrichment).all()
        assert len(enrichments) == 2
        assert {e.article_id for e in enrichments} == {
            a.id for a in session.query(Article).all()
        }
        stored = enrichments[0]
        assert stored.summary == "Summary."
        assert stored.upsc_relevance == 4
        assert stored.upsc_relevant is True
        assert stored.model  # populated from settings.anthropic_model
        assert stored.prelims_questions[0]["question"] == "Q?"


def test_run_enrich_skips_already_enriched_articles(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        article = _make_article(1, ministry)
        session.add(article)
        session.flush()
        session.add(
            Enrichment(
                article_id=article.id,
                summary="Already done.",
                context="Already done.",
                upsc_relevant=False,
                syllabus_topics=[],
                prelims_questions=[],
                mains_questions=[],
                model="claude-sonnet-5",
            )
        )

    calls: list[int] = []

    def _tracking_enrich(**kwargs):
        calls.append(1)
        return _sample_enrichment()

    monkeypatch.setattr("pib_agent.enrichment.pipeline.enrich_article", _tracking_enrich)

    stats = run_enrich(session_scope=session_scope_factory)

    assert stats.pending == 0
    assert stats.enriched == 0
    assert calls == []

    with session_scope_factory() as session:
        stored = session.query(Enrichment).one()
        assert stored.summary == "Already done."  # untouched


def test_run_enrich_continues_after_one_failure(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        session.add_all(
            [
                _make_article(1, ministry, title="Fails"),
                _make_article(2, ministry, title="Succeeds"),
            ]
        )

    def _flaky_enrich(*, title, **kwargs):
        if title == "Fails":
            raise EnrichmentError("simulated failure")
        return _sample_enrichment()

    monkeypatch.setattr("pib_agent.enrichment.pipeline.enrich_article", _flaky_enrich)

    stats = run_enrich(session_scope=session_scope_factory)

    assert stats.pending == 2
    assert stats.enriched == 1
    assert stats.failed == 1

    with session_scope_factory() as session:
        failed_article = session.query(Article).filter_by(title="Fails").one()
        assert stats.failed_article_ids == [failed_article.id]
        assert session.query(Enrichment).count() == 1


def test_run_enrich_marks_irrelevant_articles_with_empty_upsc_fields(
    monkeypatch, session_scope_factory
):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        session.add(_make_article(1, ministry))

    monkeypatch.setattr(
        "pib_agent.enrichment.pipeline.enrich_article",
        lambda **kwargs: _sample_enrichment(relevant=False),
    )

    run_enrich(session_scope=session_scope_factory)

    with session_scope_factory() as session:
        stored = session.query(Enrichment).one()
        assert stored.upsc_relevant is False
        assert stored.syllabus_topics == []
        assert stored.prelims_questions == []
        assert stored.mains_questions == []


def _enrich_one_scored(monkeypatch, session_scope_factory, score: int, threshold: int = 3):
    """Enrich a single article at `score` with the given relevance threshold."""
    from pib_agent.config import Settings
    from pib_agent.enrichment import pipeline as enrich_pipeline

    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of Finance", slug="ministry-of-finance")
        session.add(_make_article(1, ministry))

    settings = Settings(_env_file=None, upsc_relevance_threshold=threshold)
    monkeypatch.setattr(enrich_pipeline, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "pib_agent.enrichment.pipeline.enrich_article",
        lambda **kwargs: _sample_enrichment(score=score),
    )

    run_enrich(session_scope=session_scope_factory)

    with session_scope_factory() as session:
        return session.query(Enrichment).one()


@pytest.mark.parametrize(
    ("score", "expected_relevant"),
    [(1, False), (2, False), (3, True), (4, True), (5, True)],
)
def test_upsc_relevant_is_derived_from_score_and_threshold(
    monkeypatch, session_scope_factory, score, expected_relevant
):
    """The boolean is computed from the score, not asked for directly.

    Claude makes one graded judgment; the pass/fail line is ours. At the
    default threshold of 3, a 2 is stored but doesn't count as relevant.
    """
    stored = _enrich_one_scored(monkeypatch, session_scope_factory, score=score)

    assert stored.upsc_relevance == score
    assert stored.upsc_relevant is expected_relevant


def test_raising_the_threshold_narrows_what_counts_as_relevant(
    monkeypatch, session_scope_factory
):
    """A 3 passes at the default bar and fails once the bar moves to 4.

    This is the point of storing the score: notification strictness becomes a
    config change rather than a prompt rewrite plus a full re-enrichment.
    """
    stored = _enrich_one_scored(monkeypatch, session_scope_factory, score=3, threshold=4)

    assert stored.upsc_relevance == 3
    assert stored.upsc_relevant is False


def test_score_outside_one_to_five_is_rejected():
    """The 1-5 range is enforced by the schema, so a bad rating never reaches the DB."""
    with pytest.raises(ValidationError):
        _sample_enrichment(score=0)
    with pytest.raises(ValidationError):
        _sample_enrichment(score=6)
