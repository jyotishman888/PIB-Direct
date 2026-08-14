from datetime import datetime

import numpy as np
import pytest

from pib_agent.db.models import Article, ArticleLink, Embedding, Enrichment, Ministry
from pib_agent.similarity.client import SimilarityError
from pib_agent.similarity.pipeline import run_similarity
from pib_agent.similarity.schema import RelatedLink, SimilarityResult
from pib_agent.similarity.vectors import bytes_to_vector

VEC_SOLAR_A = np.array([1.0, 0.0, 0.0], dtype=np.float32)
VEC_SOLAR_B = np.array([0.9, 0.4358899, 0.0], dtype=np.float32)  # dot(A, B) ~= 0.9
VEC_UNRELATED = np.array([0.0, 0.0, 1.0], dtype=np.float32)  # dot(A, unrelated) = 0.0


def _make_article(prid: int, ministry: Ministry, title: str) -> Article:
    return Article(
        prid=prid,
        ministry=ministry,
        title=title,
        subtitle=None,
        body_text="Body text.",
        body_html="<p>Body text.</p>",
        pib_office="PIB Delhi",
        release_datetime=datetime(2026, 8, prid % 28 + 1, 12, 0),
        source_url=f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}",
    )


def _make_enrichment(article: Article, summary: str) -> Enrichment:
    return Enrichment(
        article=article,
        summary=summary,
        context="Context.",
        upsc_relevant=True,
        syllabus_topics=["GS Paper 3 - Economy"],
        prelims_questions=[],
        mains_questions=[],
        model="claude-sonnet-5",
    )


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("pib_agent.similarity.pipeline.time.sleep", lambda _seconds: None)


def test_run_similarity_embeds_only_enriched_articles(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        enriched = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(enriched, "Solar A summary."))
        session.add(_make_article(2, ministry, "Not yet enriched"))  # no Enrichment row

    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.embed_text", lambda text: VEC_SOLAR_A
    )
    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.find_related_links",
        lambda **kwargs: pytest.fail("should not call Claude with zero candidates"),
    )

    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.embed_pending == 1
    assert stats.embedded == 1

    with session_scope_factory() as session:
        embeddings = session.query(Embedding).all()
        assert len(embeddings) == 1
        assert embeddings[0].article_id == 1
        np.testing.assert_array_almost_equal(bytes_to_vector(embeddings[0].vector), VEC_SOLAR_A)


def test_run_similarity_skips_claude_when_no_candidates(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        article = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(article, "Solar A summary."))

    monkeypatch.setattr("pib_agent.similarity.pipeline.embed_text", lambda text: VEC_SOLAR_A)
    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.find_related_links",
        lambda **kwargs: pytest.fail("should not call Claude with zero candidates"),
    )

    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.link_pending == 1
    assert stats.linked == 1
    assert stats.links_created == 0

    with session_scope_factory() as session:
        embedding = session.query(Embedding).one()
        assert embedding.linked_at is not None
        assert embedding.linked_model is None
        assert session.query(ArticleLink).count() == 0


def test_run_similarity_creates_link_for_related_candidate(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        first = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(first, "Solar A summary."))
        second = _make_article(2, ministry, "Solar B")
        session.add(_make_enrichment(second, "Solar B summary."))

    def fake_embed(text: str) -> np.ndarray:
        return VEC_SOLAR_A if "Solar A" in text else VEC_SOLAR_B

    monkeypatch.setattr("pib_agent.similarity.pipeline.embed_text", fake_embed)
    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.find_related_links",
        lambda **kwargs: SimilarityResult(
            related_links=[
                RelatedLink(candidate_index=0, relationship="Both concern solar capacity growth.")
            ]
        ),
    )

    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.embedded == 2
    assert stats.linked == 2
    assert stats.links_created == 1

    with session_scope_factory() as session:
        link = session.query(ArticleLink).one()
        assert link.article_id == 2
        assert link.related_article_id == 1
        assert link.relationship_note == "Both concern solar capacity growth."


def test_run_similarity_skips_dissimilar_candidates_without_calling_claude(
    monkeypatch, session_scope_factory
):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        first = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(first, "Solar A summary."))
        second = _make_article(2, ministry, "Unrelated Topic")
        session.add(_make_enrichment(second, "Unrelated summary."))

    def fake_embed(text: str) -> np.ndarray:
        return VEC_SOLAR_A if "Solar A" in text else VEC_UNRELATED

    monkeypatch.setattr("pib_agent.similarity.pipeline.embed_text", fake_embed)
    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.find_related_links",
        lambda **kwargs: pytest.fail("should not call Claude below the similarity threshold"),
    )

    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.linked == 2
    assert stats.links_created == 0
    with session_scope_factory() as session:
        assert session.query(ArticleLink).count() == 0


def test_run_similarity_skips_out_of_range_candidate_index(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        first = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(first, "Solar A summary."))
        second = _make_article(2, ministry, "Solar B")
        session.add(_make_enrichment(second, "Solar B summary."))

    def fake_embed(text: str) -> np.ndarray:
        return VEC_SOLAR_A if "Solar A" in text else VEC_SOLAR_B

    monkeypatch.setattr("pib_agent.similarity.pipeline.embed_text", fake_embed)
    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.find_related_links",
        lambda **kwargs: SimilarityResult(
            related_links=[RelatedLink(candidate_index=5, relationship="Hallucinated index.")]
        ),
    )

    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.linked == 2
    assert stats.links_created == 0
    with session_scope_factory() as session:
        assert session.query(ArticleLink).count() == 0
        # the out-of-range response still counts as a completed (not failed) check
        embedding = session.query(Embedding).filter_by(article_id=2).one()
        assert embedding.linked_at is not None


def test_run_similarity_leaves_failed_articles_unlinked_for_retry(
    monkeypatch, session_scope_factory
):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        first = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(first, "Solar A summary."))
        second = _make_article(2, ministry, "Solar B")
        session.add(_make_enrichment(second, "Solar B summary."))

    def fake_embed(text: str) -> np.ndarray:
        return VEC_SOLAR_A if "Solar A" in text else VEC_SOLAR_B

    monkeypatch.setattr("pib_agent.similarity.pipeline.embed_text", fake_embed)

    def failing_find(**kwargs):
        raise SimilarityError("simulated failure")

    monkeypatch.setattr("pib_agent.similarity.pipeline.find_related_links", failing_find)

    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.link_failed == 1
    assert stats.link_failed_article_ids == [2]

    with session_scope_factory() as session:
        embedding = session.query(Embedding).filter_by(article_id=2).one()
        assert embedding.linked_at is None  # left pending so a future run retries it


def test_run_similarity_is_idempotent(monkeypatch, session_scope_factory):
    with session_scope_factory() as session:
        ministry = Ministry(name="Ministry of New and Renewable Energy", slug="mnre")
        article = _make_article(1, ministry, "Solar A")
        session.add(_make_enrichment(article, "Solar A summary."))

    monkeypatch.setattr("pib_agent.similarity.pipeline.embed_text", lambda text: VEC_SOLAR_A)
    calls: list[int] = []
    monkeypatch.setattr(
        "pib_agent.similarity.pipeline.find_related_links",
        lambda **kwargs: calls.append(1),
    )

    run_similarity(session_scope=session_scope_factory)
    stats = run_similarity(session_scope=session_scope_factory)

    assert stats.embed_pending == 0
    assert stats.link_pending == 0
    assert calls == []

    with session_scope_factory() as session:
        assert session.query(Embedding).count() == 1
