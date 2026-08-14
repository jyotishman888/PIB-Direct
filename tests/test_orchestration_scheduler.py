import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import pib_agent.orchestration.scheduler as scheduler_module


def _fake_settings(
    *,
    scheduler_enabled: bool,
    scheduler_interval_minutes: int = 30,
    scheduler_start_hour_ist: int = 9,
    scheduler_end_hour_ist: int = 21,
    scheduler_timezone: str = "Asia/Kolkata",
):
    return type(
        "FakeSettings",
        (),
        {
            "scheduler_enabled": scheduler_enabled,
            "scheduler_interval_minutes": scheduler_interval_minutes,
            "scheduler_start_hour_ist": scheduler_start_hour_ist,
            "scheduler_end_hour_ist": scheduler_end_hour_ist,
            "scheduler_timezone": scheduler_timezone,
        },
    )()


@pytest.fixture(autouse=True)
def _reset_scheduler_state():
    scheduler_module._scheduler = None
    yield
    scheduler_module.stop_scheduler()


def _patch_now(monkeypatch, fixed):
    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            return fixed

    monkeypatch.setattr(scheduler_module, "datetime", _FakeDatetime)


def _stub_run_pipeline(monkeypatch):
    """start_scheduler() fires an immediate startup job on a real background
    thread. Stub run_pipeline AND hand back a threading.Event set when it's
    called, so every test that starts the real scheduler can deterministically
    wait for that job to run against the stub before returning — otherwise a
    slow-to-dispatch job could still be in flight when monkeypatch reverts at
    test teardown and end up calling the real (network-hitting) run_pipeline
    from an orphaned thread. This isn't a hypothetical: it happened once
    during development, leaving a stray live pipeline run in the DB.
    """

    class _FakeResult:
        id = 1
        status = "success"

    calls: list[str] = []
    called = threading.Event()

    def _fake(trigger):
        calls.append(trigger)
        called.set()
        return _FakeResult()

    monkeypatch.setattr(scheduler_module, "run_pipeline", _fake)
    return calls, called


def test_build_scheduler_registers_one_job(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )

    scheduler = scheduler_module.build_scheduler()
    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "pib_agent_pipeline"


def test_build_scheduler_supports_hour_plus_intervals(monkeypatch):
    # A cron minute field only spans 0-59, so `*/60` (or anything >= 60)
    # used to crash at startup — this is exactly the bug a real 60-minute
    # interval setting exposed. IntervalTrigger has no such limit.
    monkeypatch.setattr(
        scheduler_module,
        "get_settings",
        lambda: _fake_settings(scheduler_enabled=True, scheduler_interval_minutes=60),
    )

    scheduler = scheduler_module.build_scheduler()
    jobs = scheduler.get_jobs()

    tz = ZoneInfo("Asia/Kolkata")
    start = datetime(2026, 1, 1, 9, 0, tzinfo=tz)
    next_fire = jobs[0].trigger.get_next_fire_time(start, start)
    assert next_fire == datetime(2026, 1, 1, 10, 0, tzinfo=tz)


def test_within_active_window_respects_configured_hours(monkeypatch):
    settings = _fake_settings(
        scheduler_enabled=True, scheduler_start_hour_ist=9, scheduler_end_hour_ist=21
    )
    tz = ZoneInfo("Asia/Kolkata")

    _patch_now(monkeypatch, datetime(2026, 1, 1, 9, 0, tzinfo=tz))
    assert scheduler_module._within_active_window(settings) is True

    _patch_now(monkeypatch, datetime(2026, 1, 1, 21, 59, tzinfo=tz))
    assert scheduler_module._within_active_window(settings) is True

    _patch_now(monkeypatch, datetime(2026, 1, 1, 8, 59, tzinfo=tz))
    assert scheduler_module._within_active_window(settings) is False

    _patch_now(monkeypatch, datetime(2026, 1, 1, 22, 0, tzinfo=tz))
    assert scheduler_module._within_active_window(settings) is False


def test_run_scheduled_job_skips_outside_window(monkeypatch):
    tz = ZoneInfo("Asia/Kolkata")
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    _patch_now(monkeypatch, datetime(2026, 1, 1, 3, 0, tzinfo=tz))

    calls = []
    monkeypatch.setattr(scheduler_module, "run_pipeline", lambda trigger: calls.append(trigger))

    scheduler_module._run_scheduled_job()

    assert calls == []


def test_run_scheduled_job_runs_inside_window(monkeypatch):
    tz = ZoneInfo("Asia/Kolkata")
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    _patch_now(monkeypatch, datetime(2026, 1, 1, 12, 0, tzinfo=tz))
    calls, _called = _stub_run_pipeline(monkeypatch)

    scheduler_module._run_scheduled_job()

    assert calls == ["scheduled"]


def test_run_startup_job_bypasses_active_window(monkeypatch):
    # Directly exercises the "startup always runs, window or not" rule
    # without touching the real scheduler/threading at all.
    tz = ZoneInfo("Asia/Kolkata")
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    _patch_now(monkeypatch, datetime(2026, 1, 1, 3, 0, tzinfo=tz))
    calls, _called = _stub_run_pipeline(monkeypatch)

    scheduler_module._run_startup_job()

    assert calls == ["startup"]


def test_start_scheduler_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=False)
    )

    result = scheduler_module.start_scheduler()

    assert result is None
    assert scheduler_module._scheduler is None


def test_start_scheduler_then_stop_scheduler(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    _calls, called = _stub_run_pipeline(monkeypatch)

    scheduler = scheduler_module.start_scheduler()
    called.wait(timeout=3)  # let the immediate startup job land on the stub before proceeding

    assert scheduler is not None
    assert scheduler.running is True
    assert scheduler_module._scheduler is scheduler

    scheduler_module.stop_scheduler()

    assert scheduler.running is False
    assert scheduler_module._scheduler is None


def test_start_scheduler_is_idempotent(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    _calls, called = _stub_run_pipeline(monkeypatch)

    first = scheduler_module.start_scheduler()
    second = scheduler_module.start_scheduler()
    called.wait(timeout=3)

    assert first is second


def test_start_scheduler_runs_pipeline_immediately(monkeypatch):
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    calls, called = _stub_run_pipeline(monkeypatch)

    scheduler_module.start_scheduler()

    assert called.wait(timeout=5)
    assert calls == ["startup"]


def test_start_scheduler_immediate_run_bypasses_active_window(monkeypatch):
    # Outside the configured 9-21 window — the recurring job would skip,
    # but the one-off startup job must still fire.
    monkeypatch.setattr(
        scheduler_module, "get_settings", lambda: _fake_settings(scheduler_enabled=True)
    )
    _patch_now(monkeypatch, datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo("Asia/Kolkata")))
    calls, called = _stub_run_pipeline(monkeypatch)

    scheduler_module.start_scheduler()

    assert called.wait(timeout=5)
    assert calls == ["startup"]
