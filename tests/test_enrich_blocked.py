"""An account-level failure must stop the pass, not burn the whole backlog."""

import pib_agent.enrichment.pipeline as pipeline_module
from pib_agent.enrichment.client import EnrichmentBlockedError, EnrichmentError
from pib_agent.enrichment.pipeline import run_enrich


def _pending(n):
    return [
        {
            "id": i,
            "title": f"Article {i}",
            "subtitle": None,
            "body_text": "body",
            "ministry_name": "Ministry",
            "release_datetime": None,
            "pib_office": None,
        }
        for i in range(1, n + 1)
    ]


def _patch(monkeypatch, side_effect, count=5):
    monkeypatch.setattr(pipeline_module, "_load_pending_articles", lambda session: _pending(count))
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _: None)
    calls: list[int] = []

    def _enrich_one(article, session_scope, stats):
        calls.append(article["id"])
        side_effect(article, stats)

    monkeypatch.setattr(pipeline_module, "_enrich_one", _enrich_one)
    return calls


def test_blocked_error_stops_the_pass(monkeypatch, session_scope_factory):
    def _blocked(article, stats):
        raise EnrichmentBlockedError("Your credit balance is too low")

    calls = _patch(monkeypatch, _blocked, count=5)

    stats = run_enrich(session_scope=session_scope_factory)

    # one attempt, not five: the other four would fail identically
    assert calls == [1]
    assert stats.pending == 5
    assert stats.failed == 1
    assert "credit balance" in stats.blocked


def test_ordinary_failures_still_run_the_whole_backlog(monkeypatch, session_scope_factory):
    def _one_bad(article, stats):
        if article["id"] == 2:
            stats.failed += 1
            stats.failed_article_ids.append(article["id"])
        else:
            stats.enriched += 1

    calls = _patch(monkeypatch, _one_bad, count=5)

    stats = run_enrich(session_scope=session_scope_factory)

    assert calls == [1, 2, 3, 4, 5]
    assert stats.enriched == 4 and stats.failed == 1
    assert stats.blocked is None


def test_blocked_is_a_subclass_so_existing_handlers_still_catch_it():
    assert issubclass(EnrichmentBlockedError, EnrichmentError)
