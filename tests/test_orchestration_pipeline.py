from datetime import UTC, datetime, timedelta

import pytest

import pib_agent.orchestration.pipeline as pipeline_module
from pib_agent.db.models import PipelineRun
from pib_agent.enrichment.pipeline import EnrichStats
from pib_agent.orchestration.pipeline import (
    PipelineAlreadyRunningError,
    mark_interrupted_runs,
    run_pipeline,
    start_pipeline_run,
)
from pib_agent.publish import PublishStats
from pib_agent.scraper.pipeline import ScrapeStats
from pib_agent.similarity.pipeline import SimilarityStats
from pib_agent.study.pipeline import StudyStats
from pib_agent.telegram.bot import TelegramConfigError
from pib_agent.telegram.notify import NotifyStats


def _patch_all_success(monkeypatch):
    monkeypatch.setattr(
        pipeline_module, "run_scrape", lambda: ScrapeStats(listed=1, new_articles=1)
    )
    monkeypatch.setattr(
        pipeline_module, "run_enrich", lambda: EnrichStats(pending=1, enriched=1)
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_similarity",
        lambda: SimilarityStats(embed_pending=1, embedded=1, link_pending=1, linked=1),
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_notify",
        lambda: NotifyStats(pending=1, notified_articles=1, messages_sent=1),
    )
    monkeypatch.setattr(
        pipeline_module, "run_study", lambda: StudyStats(pending=1, analysed=1)
    )
    monkeypatch.setattr(
        pipeline_module,
        "run_publish",
        lambda: PublishStats(articles=1, changed=True, pushed=True),
    )


def test_run_pipeline_all_success(monkeypatch, session_scope_factory):
    _patch_all_success(monkeypatch)

    result = run_pipeline("manual", session_scope=session_scope_factory)

    assert result.status == "success"
    assert [s.name for s in result.stages] == [
        "scrape",
        "enrich",
        "notify",
        "link",
        "study",
        "publish",
    ]
    assert all(s.status == "success" for s in result.stages)

    with session_scope_factory() as session:
        run = session.get(PipelineRun, result.id)
        assert run.status == "success"
        assert run.trigger == "manual"
        assert run.finished_at is not None
        assert len(run.stages) == 6


def test_run_pipeline_stage_failure_is_isolated(monkeypatch, session_scope_factory):
    calls: list[str] = []

    def _boom():
        calls.append("scrape")
        raise RuntimeError("PIB is down")

    def _enrich():
        calls.append("enrich")
        return EnrichStats()

    def _link():
        calls.append("link")
        return SimilarityStats()

    def _notify():
        calls.append("notify")
        return NotifyStats()

    def _study():
        calls.append("study")
        return StudyStats()

    def _publish():
        calls.append("publish")
        return PublishStats(articles=0, changed=False, pushed=False)

    monkeypatch.setattr(pipeline_module, "run_scrape", _boom)
    monkeypatch.setattr(pipeline_module, "run_enrich", _enrich)
    monkeypatch.setattr(pipeline_module, "run_similarity", _link)
    monkeypatch.setattr(pipeline_module, "run_notify", _notify)
    monkeypatch.setattr(pipeline_module, "run_study", _study)
    monkeypatch.setattr(pipeline_module, "run_publish", _publish)

    result = run_pipeline("manual", session_scope=session_scope_factory)

    # every stage still ran despite scrape blowing up
    assert calls == ["scrape", "enrich", "notify", "link", "study", "publish"]
    assert result.status == "failed"
    scrape_stage = result.stages[0]
    assert scrape_stage.status == "failed"
    assert "PIB is down" in scrape_stage.error
    assert all(s.status == "success" for s in result.stages[1:])


def test_run_pipeline_partial_failure(monkeypatch, session_scope_factory):
    monkeypatch.setattr(pipeline_module, "run_scrape", lambda: ScrapeStats(listed=2, failed=1))
    monkeypatch.setattr(pipeline_module, "run_enrich", lambda: EnrichStats())
    monkeypatch.setattr(pipeline_module, "run_similarity", lambda: SimilarityStats())
    monkeypatch.setattr(pipeline_module, "run_notify", lambda: NotifyStats())
    monkeypatch.setattr(pipeline_module, "run_study", lambda: StudyStats())

    result = run_pipeline("manual", session_scope=session_scope_factory)

    assert result.stages[0].status == "partial_failure"
    assert result.status == "partial_failure"


def test_run_pipeline_notify_skipped_without_token(monkeypatch, session_scope_factory):
    def _no_token():
        raise TelegramConfigError("TELEGRAM_BOT_TOKEN is not set.")

    monkeypatch.setattr(pipeline_module, "run_scrape", lambda: ScrapeStats())
    monkeypatch.setattr(pipeline_module, "run_enrich", lambda: EnrichStats())
    monkeypatch.setattr(pipeline_module, "run_similarity", lambda: SimilarityStats())
    monkeypatch.setattr(pipeline_module, "run_notify", _no_token)
    monkeypatch.setattr(pipeline_module, "run_study", lambda: StudyStats())

    result = run_pipeline("manual", session_scope=session_scope_factory)

    notify_stage = next(s for s in result.stages if s.name == "notify")
    assert notify_stage.status == "skipped"
    # a deliberately-skipped stage doesn't count as a failure of the run
    assert result.status == "success"


def test_notify_runs_before_link(monkeypatch, session_scope_factory):
    """Subscribers shouldn't wait out the similarity pass to hear about a release.

    Nothing in a notification is derived from article links, so notify is
    ordered ahead of link — on a full backlog that's the difference between
    delivery in seconds and delivery ~20 minutes later.
    """
    calls: list[str] = []

    def _record(name, stats):
        def _fn():
            calls.append(name)
            return stats

        return _fn

    monkeypatch.setattr(pipeline_module, "run_scrape", _record("scrape", ScrapeStats()))
    monkeypatch.setattr(pipeline_module, "run_enrich", _record("enrich", EnrichStats()))
    monkeypatch.setattr(pipeline_module, "run_similarity", _record("link", SimilarityStats()))
    monkeypatch.setattr(pipeline_module, "run_notify", _record("notify", NotifyStats()))

    run_pipeline("manual", session_scope=session_scope_factory)

    assert calls.index("notify") < calls.index("link")
    assert calls.index("enrich") < calls.index("notify")


def test_failed_run_raises_an_ops_alert(monkeypatch, session_scope_factory, ops_alerts):
    """A silent failure is the failure mode that actually hurt.

    PIB changed its listing markup and every hourly run failed for ~7 hours
    with no signal anywhere except a log nobody was reading.
    """
    def _boom():
        raise RuntimeError("PIB is down")

    monkeypatch.setattr(pipeline_module, "run_scrape", _boom)
    monkeypatch.setattr(pipeline_module, "run_enrich", lambda: EnrichStats())
    monkeypatch.setattr(pipeline_module, "run_similarity", lambda: SimilarityStats())
    monkeypatch.setattr(pipeline_module, "run_notify", lambda: NotifyStats())

    result = run_pipeline("scheduled", session_scope=session_scope_factory)

    assert result.status == "failed"
    assert len(ops_alerts) == 1
    subject, body = ops_alerts[0]
    assert "failed" in subject
    assert "scheduled" in subject
    assert "PIB is down" in body


def test_partial_failure_also_alerts(monkeypatch, session_scope_factory, ops_alerts):
    monkeypatch.setattr(pipeline_module, "run_scrape", lambda: ScrapeStats(listed=2, failed=1))
    monkeypatch.setattr(pipeline_module, "run_enrich", lambda: EnrichStats())
    monkeypatch.setattr(pipeline_module, "run_similarity", lambda: SimilarityStats())
    monkeypatch.setattr(pipeline_module, "run_notify", lambda: NotifyStats())
    monkeypatch.setattr(pipeline_module, "run_study", lambda: StudyStats())

    run_pipeline("manual", session_scope=session_scope_factory)

    assert len(ops_alerts) == 1
    assert "partial_failure" in ops_alerts[0][0]


def test_successful_run_stays_quiet(monkeypatch, session_scope_factory, ops_alerts):
    """No news is good news — a healthy run must not page anyone."""
    _patch_all_success(monkeypatch)

    run_pipeline("scheduled", session_scope=session_scope_factory)

    assert ops_alerts == []


def test_skipped_stage_does_not_alert(monkeypatch, session_scope_factory, ops_alerts):
    """A deliberately-skipped notify (no token configured) isn't a fault."""
    def _no_token():
        raise TelegramConfigError("TELEGRAM_BOT_TOKEN is not set.")

    monkeypatch.setattr(pipeline_module, "run_scrape", lambda: ScrapeStats())
    monkeypatch.setattr(pipeline_module, "run_enrich", lambda: EnrichStats())
    monkeypatch.setattr(pipeline_module, "run_similarity", lambda: SimilarityStats())
    monkeypatch.setattr(pipeline_module, "run_notify", _no_token)
    monkeypatch.setattr(pipeline_module, "run_study", lambda: StudyStats())

    result = run_pipeline("manual", session_scope=session_scope_factory)

    assert result.status == "success"
    assert ops_alerts == []


def test_start_pipeline_run_raises_when_already_running(session_scope_factory):
    """A second run must decline rather than double-spend on Claude/Telegram."""
    from pib_agent.orchestration.run_lock import RunLock

    held = RunLock()
    assert held.acquire()
    try:
        with pytest.raises(PipelineAlreadyRunningError):
            start_pipeline_run("manual", session_scope=session_scope_factory)
    finally:
        held.release()


def test_run_lock_is_reentrant_across_sequential_runs(monkeypatch, session_scope_factory):
    """Releasing must actually free the lock, or the first run wedges the app.

    Guards the failure mode where a lock is taken per-run but never handed
    back: run one succeeds, every later run raises "already in progress"
    forever.
    """
    _patch_all_success(monkeypatch)

    first = run_pipeline("manual", session_scope=session_scope_factory)
    second = run_pipeline("manual", session_scope=session_scope_factory)

    assert first.status == "success"
    assert second.status == "success"
    assert first.id != second.id


def _running_row(session_scope_factory, *, age: timedelta) -> int:
    with session_scope_factory() as session:
        run = PipelineRun(
            trigger="scheduled",
            status="running",
            stages=[],
            started_at=datetime.now(UTC) - age,
        )
        session.add(run)
        session.flush()
        return run.id


def test_mark_interrupted_runs_marks_stale_running_rows(session_scope_factory):
    stale_id = _running_row(session_scope_factory, age=timedelta(hours=6))

    fixed = mark_interrupted_runs(session_scope=session_scope_factory)

    assert fixed == 1
    with session_scope_factory() as session:
        run = session.get(PipelineRun, stale_id)
        assert run.status == "failed"
        assert run.finished_at is not None
        assert "Interrupted" in run.error


def test_mark_interrupted_runs_leaves_a_live_run_alone(session_scope_factory):
    """Starting the API must not declare the scheduled task's live run dead.

    The run lock is per-process, so on SQLite `serve` and `run` are separate
    processes and a young "running" row may still be genuinely working.
    """
    live_id = _running_row(session_scope_factory, age=timedelta(minutes=5))

    assert mark_interrupted_runs(session_scope=session_scope_factory) == 0
    with session_scope_factory() as session:
        assert session.get(PipelineRun, live_id).status == "running"
