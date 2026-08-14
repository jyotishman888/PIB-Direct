import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pib_agent.config import Settings, get_settings
from pib_agent.orchestration.pipeline import PipelineAlreadyRunningError, run_pipeline

logger = logging.getLogger(__name__)

_JOB_ID = "pib_agent_pipeline"
_STARTUP_JOB_ID = "pib_agent_pipeline_startup"
_scheduler: BackgroundScheduler | None = None


def _within_active_window(settings: Settings) -> bool:
    now = datetime.now(ZoneInfo(settings.scheduler_timezone))
    return settings.scheduler_start_hour_ist <= now.hour <= settings.scheduler_end_hour_ist


def _run_pipeline_job(trigger: str, *, bypass_window: bool = False) -> None:
    if not bypass_window and not _within_active_window(get_settings()):
        logger.debug("Scheduled tick outside the active window; skipping.")
        return
    try:
        result = run_pipeline(trigger)
        logger.info("%s pipeline run %s finished: status=%s", trigger, result.id, result.status)
    except PipelineAlreadyRunningError:
        logger.info("%s pipeline run skipped: a run is already in progress.", trigger)
    except Exception:
        logger.exception("%s pipeline run crashed unexpectedly.", trigger)


def _run_scheduled_job() -> None:
    _run_pipeline_job("scheduled")


def _run_startup_job() -> None:
    # Starting the app is an explicit action, not a passive periodic tick —
    # always check for new releases right away rather than making the user
    # wait up to a full `scheduler_interval_minutes` for the first check,
    # regardless of what hour they happened to start it.
    _run_pipeline_job("startup", bypass_window=True)


def build_scheduler() -> BackgroundScheduler:
    """Build (but don't start) a scheduler that runs the pipeline on an interval.

    Fires every `scheduler_interval_minutes` minutes via a plain interval
    trigger (not cron) — a cron minute field only spans 0-59, so it can't
    express intervals of an hour or more; an interval trigger handles any
    value uniformly. The `scheduler_start_hour_ist`-`scheduler_end_hour_ist`
    window is enforced inside the job itself (`_within_active_window`)
    rather than the trigger, since PIB publishes during the Indian working
    day and there's nothing new to find outside those hours.
    """
    settings = get_settings()
    tz = ZoneInfo(settings.scheduler_timezone)
    scheduler = BackgroundScheduler(timezone=tz)
    trigger = IntervalTrigger(minutes=settings.scheduler_interval_minutes, timezone=tz)
    scheduler.add_job(_run_scheduled_job, trigger, id=_JOB_ID, max_instances=1, coalesce=True)
    return scheduler


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background scheduler if SCHEDULER_ENABLED=true. Idempotent.

    Also runs the pipeline once immediately (see _run_startup_job) so
    starting the app doesn't mean waiting up to a full interval before the
    first check for new releases — the recurring interval trigger takes
    over from there.
    """
    global _scheduler
    settings = get_settings()

    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false); skipping.")
        return None
    if _scheduler is not None:
        return _scheduler

    _scheduler = build_scheduler()
    _scheduler.add_job(_run_startup_job, DateTrigger(), id=_STARTUP_JOB_ID)
    _scheduler.start()
    logger.info(
        "Scheduler started: every %s minute(s) between %02d:00-%02d:00 %s "
        "(plus an immediate run now)",
        settings.scheduler_interval_minutes,
        settings.scheduler_start_hour_ist,
        settings.scheduler_end_hour_ist,
        settings.scheduler_timezone,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Stop and clear the background scheduler, if one is running. Idempotent."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped.")
