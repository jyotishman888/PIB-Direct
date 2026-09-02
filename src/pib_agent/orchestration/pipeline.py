import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from pib_agent.db import PipelineRun
from pib_agent.db import session_scope as default_session_scope
from pib_agent.enrichment import run_enrich
from pib_agent.enrichment.pipeline import EnrichStats
from pib_agent.orchestration.run_lock import RunLock
from pib_agent.publish import PublishDisabledError, PublishStats, run_publish
from pib_agent.scraper import run_scrape
from pib_agent.scraper.pipeline import ScrapeStats
from pib_agent.similarity import run_similarity
from pib_agent.similarity.pipeline import SimilarityStats
from pib_agent.study import run_study
from pib_agent.study.pipeline import StudyStats
from pib_agent.telegram import run_notify
from pib_agent.telegram.alerts import send_ops_alert
from pib_agent.telegram.bot import TelegramConfigError
from pib_agent.telegram.notify import NotifyStats

logger = logging.getLogger(__name__)

SessionScopeFn = Callable[[], AbstractContextManager[Session]]

# Only one orchestrated run (scheduled, manually triggered, or CLI) may
# execute at a time — overlapping runs would double up on PIB/Claude/Telegram
# calls for the same pending work. RunLock spans processes on Postgres (see
# run_lock.py), which matters once this is deployed and a rolling restart can
# briefly run two instances at once.
_run_lock: RunLock | None = None


class PipelineAlreadyRunningError(RuntimeError):
    """Raised when a pipeline run is requested while another is in progress."""


class _StageSkipped(Exception):
    """Internal sentinel: the stage was deliberately not run (e.g. no Telegram token)."""


@dataclass
class StageResult:
    name: str
    status: str  # "success" | "partial_failure" | "failed" | "skipped"
    summary: str | None = None
    error: str | None = None


@dataclass
class PipelineRunResult:
    id: int
    status: str  # "success" | "partial_failure" | "failed"
    stages: list[StageResult]


def _stage_failed_count(stats: object) -> int:
    return sum(
        getattr(stats, attr, 0)
        for attr in (
            "failed",
            "embed_failed",
            "link_failed",
            "messages_failed",
            "listing_sources_failed",
        )
    )


def _stage_summary(name: str, stats: object) -> str:
    if isinstance(stats, ScrapeStats):
        return (
            f"listed {stats.listed}, new {stats.new_articles}, "
            f"already known {stats.already_known}, failed {stats.failed}, "
            f"listing sources failed {stats.listing_sources_failed}"
        )
    if isinstance(stats, EnrichStats):
        summary = f"pending {stats.pending}, enriched {stats.enriched}, failed {stats.failed}"
        if stats.blocked:
            # The reason belongs in the alert; the backlog size alone reads as
            # "lots of articles are broken" when the account is the problem.
            summary += f" - stopped early: {stats.blocked}"
        return summary
    if isinstance(stats, SimilarityStats):
        return (
            f"embedded {stats.embedded}/{stats.embed_pending}, "
            f"linked {stats.linked}/{stats.link_pending}, "
            f"links created {stats.links_created}, "
            f"failed {stats.embed_failed + stats.link_failed}"
        )
    if isinstance(stats, NotifyStats):
        return (
            f"pending {stats.pending}, notified {stats.notified_articles}, "
            f"sent {stats.messages_sent}, failed {stats.messages_failed}, "
            f"dead chats removed {stats.dead_chats_removed}"
        )
    if isinstance(stats, StudyStats):
        summary = f"pending {stats.pending}, analysed {stats.analysed}, failed {stats.failed}"
        if stats.blocked:
            summary += f" - stopped early: {stats.blocked}"
        return summary
    if isinstance(stats, PublishStats):
        if not stats.changed:
            return f"bundle unchanged ({stats.articles} articles)"
        served = ", site serving" if stats.site_ok else ""
        return f"pushed {stats.articles} articles{served}"
    return str(stats)  # pragma: no cover - defensive fallback for an unrecognized stats type


def _run_notify_stage() -> NotifyStats:
    try:
        return run_notify()
    except TelegramConfigError as exc:
        raise _StageSkipped(str(exc)) from exc


def _run_publish_stage() -> PublishStats:
    try:
        return run_publish()
    except PublishDisabledError as exc:
        raise _StageSkipped(str(exc)) from exc


def _run_stage(name: str, fn: Callable[[], object], run_id: int) -> StageResult:
    logger.info("Pipeline run %s: stage %r starting", run_id, name)
    try:
        stats = fn()
    except _StageSkipped as exc:
        logger.info("Pipeline run %s: stage %r skipped (%s)", run_id, name, exc)
        return StageResult(name=name, status="skipped", summary=str(exc))
    except Exception as exc:
        logger.exception("Pipeline run %s: stage %r failed", run_id, name)
        return StageResult(name=name, status="failed", error=str(exc))

    status = "partial_failure" if _stage_failed_count(stats) else "success"
    summary = _stage_summary(name, stats)
    logger.info("Pipeline run %s: stage %r %s (%s)", run_id, name, status, summary)
    return StageResult(name=name, status=status, summary=summary)


def _alert_on_unhealthy_run(
    run_id: int, trigger: str, status: str, stages: list[StageResult]
) -> None:
    """Tell the operator when a run didn't fully succeed.

    A pipeline that fails quietly looks exactly like a pipeline with nothing
    to do, which is how a broken scraper survived ~7 hours of hourly runs
    unnoticed. Only unhealthy runs alert — a healthy one saying nothing is
    the whole point.
    """
    if status == "success":
        return

    lines = []
    for stage in stages:
        if stage.status in {"failed", "partial_failure"}:
            detail = stage.error or stage.summary or ""
            lines.append(f"{stage.name}: {stage.status}\n{detail}".strip())

    send_ops_alert(
        f"Pipeline run {run_id} ({trigger}) finished {status}",
        "\n\n".join(lines),
    )


def _overall_status(stages: list[StageResult]) -> str:
    statuses = {stage.status for stage in stages}
    if "failed" in statuses:
        return "failed"
    if "partial_failure" in statuses:
        return "partial_failure"
    return "success"


def start_pipeline_run(
    trigger: str, *, session_scope: SessionScopeFn = default_session_scope
) -> int:
    """Reserve the run slot and create a "running" PipelineRun row, returning its id.

    Raises PipelineAlreadyRunningError without touching the DB if another run
    is already in progress. On success, the caller MUST eventually call
    execute_pipeline_run with the returned id — that call releases the lock.
    """
    global _run_lock
    lock = RunLock()
    if not lock.acquire():
        raise PipelineAlreadyRunningError("A pipeline run is already in progress.")
    _run_lock = lock

    try:
        with session_scope() as session:
            run = PipelineRun(trigger=trigger, status="running", stages=[])
            session.add(run)
            session.flush()
            run_id = run.id
    except Exception:
        _run_lock.release()
        _run_lock = None
        raise

    logger.info("Pipeline run %s started (trigger=%r)", run_id, trigger)
    return run_id


def execute_pipeline_run(
    run_id: int, *, session_scope: SessionScopeFn = default_session_scope
) -> PipelineRunResult:
    """Run scrape -> enrich -> notify -> link -> study -> publish for a created run.

    Each stage is isolated: if one raises, it's recorded as failed and the
    next stage still runs against whatever earlier stages (this run or prior
    ones) already persisted. Always releases the run lock acquired by
    start_pipeline_run, even if a stage or the final DB write blows up.
    """
    try:
        stages = [
            _run_stage("scrape", run_scrape, run_id),
            _run_stage("enrich", run_enrich, run_id),
            # notify runs before link deliberately. Everything a notification
            # needs (title, ministry, summary, UPSC flag) exists the moment
            # enrichment finishes, and nothing in the message body comes from
            # similarity links — so making subscribers wait out a full linking
            # pass just delays delivery for no gain. Linking a full backlog has
            # taken ~20 minutes, which is 20 minutes of "PIB published, we
            # know, you don't".
            _run_stage("notify", _run_notify_stage, run_id),
            _run_stage("link", run_similarity, run_id),
            # study runs last: it's the most expensive stage per article and
            # nothing downstream depends on it, so a slow or failing run here
            # never delays delivery or leaves the corpus unlinked.
            _run_stage("study", run_study, run_id),
            # publish last: it turns whatever the run produced into the bundle
            # the deployed site reads, so it must see every earlier stage's
            # output. A failure here costs freshness, never data.
            _run_stage("publish", _run_publish_stage, run_id),
        ]
        overall_status = _overall_status(stages)

        trigger = "unknown"
        with session_scope() as session:
            run = session.get(PipelineRun, run_id)
            if run is not None:
                trigger = run.trigger
                run.status = overall_status
                run.finished_at = datetime.now(UTC)
                run.stages = [
                    {
                        "name": s.name,
                        "status": s.status,
                        "summary": s.summary,
                        "error": s.error,
                    }
                    for s in stages
                ]

        logger.info("Pipeline run %s finished: status=%s", run_id, overall_status)
        _alert_on_unhealthy_run(run_id, trigger, overall_status, stages)
        return PipelineRunResult(id=run_id, status=overall_status, stages=stages)
    except Exception as exc:
        logger.exception("Pipeline run %s crashed unexpectedly", run_id)
        send_ops_alert(f"Pipeline run {run_id} crashed", str(exc))
        with session_scope() as session:
            run = session.get(PipelineRun, run_id)
            if run is not None:
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                run.error = str(exc)
        raise
    finally:
        global _run_lock
        if _run_lock is not None:
            _run_lock.release()
            _run_lock = None


def run_pipeline(
    trigger: str, *, session_scope: SessionScopeFn = default_session_scope
) -> PipelineRunResult:
    """Run scrape -> enrich -> notify -> link once, end to end, and wait for it to finish.

    Convenience wrapper around start_pipeline_run + execute_pipeline_run for
    callers (CLI, scheduler) that want to block until the run completes.
    Raises PipelineAlreadyRunningError if another run is already in progress.
    """
    run_id = start_pipeline_run(trigger, session_scope=session_scope)
    return execute_pipeline_run(run_id, session_scope=session_scope)


# A "running" row is only evidence of a crash once it is too old to be a live
# run. This used to assume any such row at startup was stale, on the grounds
# that the run lock is in-memory so a run cannot span a restart - but the lock
# is per-*process*, and on SQLite the scheduled `pib-agent run` is a different
# process from `pib-agent serve`. Starting the server while the hourly run was
# mid-pipeline marked that live run failed and fired an ops alert; the run then
# finished and overwrote its own status, so the history briefly lied.
#
# The longest genuine run observed is ~59 minutes (a large enrichment backlog),
# so three hours is comfortably dead. Nothing gates on the status - it is
# reporting only - so cleaning up late costs nothing, while cleaning up early
# corrupts a run that is still working.
_STALE_RUN_AFTER = timedelta(hours=3)


def mark_interrupted_runs(*, session_scope: SessionScopeFn = default_session_scope) -> int:
    """Mark runs left "running" by a crashed process as failed.

    Safe to call on every app startup, and safe to call while another process
    is mid-run: only rows older than _STALE_RUN_AFTER are touched. Returns the
    number of rows fixed up.
    """
    now = datetime.now(UTC)
    cutoff = now - _STALE_RUN_AFTER
    fixed = 0
    with session_scope() as session:
        for run in session.query(PipelineRun).filter_by(status="running").all():
            started = run.started_at
            # SQLite hands back a naive datetime for a timezone-aware column,
            # and every write is UTC, so read it as such rather than comparing
            # naive against aware and raising.
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            if started is not None and started > cutoff:
                continue  # young enough that a live process may still own it

            run.status = "failed"
            run.finished_at = now
            run.error = "Interrupted (process restarted before this run finished)."
            fixed += 1

    if fixed:
        logger.warning("Marked %s stale pipeline run(s) as failed on startup", fixed)
    return fixed
