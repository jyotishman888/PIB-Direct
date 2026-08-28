import pytest

import pib_agent.publish as publish_module
from pib_agent.config import get_settings
from pib_agent.export_static import ExportResult
from pib_agent.publish import PublishDisabledError, run_publish


@pytest.fixture
def _enabled(monkeypatch):
    monkeypatch.setenv("PUBLISH_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_export(monkeypatch, articles=3, latest="2026-08-24"):
    monkeypatch.setattr(
        publish_module,
        "export_static",
        lambda out_dir, session, days=30: ExportResult(
            out_dir=out_dir,
            article_count=articles,
            ministry_count=1,
            latest_date=latest,
            window_days=days,
        ),
    )
    monkeypatch.setattr(publish_module, "session_scope", _null_scope)


class _null_scope:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _record_git(monkeypatch, status_output=""):
    calls: list[tuple[str, ...]] = []

    def _git(*args: str) -> str:
        calls.append(args)
        return status_output if args[0] == "status" else ""

    monkeypatch.setattr(publish_module, "_git", _git)
    return calls


def test_disabled_raises_so_the_stage_records_as_skipped():
    with pytest.raises(PublishDisabledError):
        run_publish()


def test_unchanged_bundle_is_not_committed(monkeypatch, _enabled):
    _fake_export(monkeypatch)
    calls = _record_git(monkeypatch, status_output="")

    stats = run_publish()

    assert stats.changed is False and stats.pushed is False
    assert [c[0] for c in calls] == ["add", "status"]


def test_changed_bundle_is_committed_and_pushed(monkeypatch, _enabled):
    _fake_export(monkeypatch)
    calls = _record_git(monkeypatch, status_output=" M frontend/public/data/index.json")

    stats = run_publish()

    assert stats.changed is True and stats.pushed is True
    assert [c[0] for c in calls] == ["add", "status", "commit", "push"]


def test_git_writes_are_limited_to_the_export_directory(monkeypatch, _enabled):
    """A run must never sweep up unrelated work in progress."""
    _fake_export(monkeypatch)
    calls = _record_git(monkeypatch, status_output=" M frontend/public/data/index.json")

    run_publish()

    for call in calls:
        if call[0] in {"add", "commit", "status"}:
            assert "--" in call, call
            assert call[call.index("--") + 1] == "frontend/public/data"


def test_site_check_failure_fails_the_publish(monkeypatch, _enabled):
    """A push landing says nothing about whether the site is actually served."""
    monkeypatch.setenv("SITE_URL", "https://example.invalid/")
    get_settings.cache_clear()
    _fake_export(monkeypatch)
    _record_git(monkeypatch, status_output=" M frontend/public/data/index.json")

    def _dead(url):
        raise publish_module.PublishUnreachableError(f"{url} returned HTTP 404")

    monkeypatch.setattr(publish_module, "_check_site", _dead)

    with pytest.raises(publish_module.PublishUnreachableError):
        run_publish()


def test_site_check_success_is_recorded(monkeypatch, _enabled):
    monkeypatch.setenv("SITE_URL", "https://example.invalid/")
    get_settings.cache_clear()
    _fake_export(monkeypatch)
    _record_git(monkeypatch, status_output=" M frontend/public/data/index.json")
    monkeypatch.setattr(publish_module, "_check_site", lambda url: None)

    assert run_publish().site_ok is True


def test_site_is_not_checked_when_unset(monkeypatch, _enabled):
    _fake_export(monkeypatch)
    _record_git(monkeypatch, status_output=" M frontend/public/data/index.json")

    def _boom(url):  # pragma: no cover - must never run
        raise AssertionError("site check ran without SITE_URL set")

    monkeypatch.setattr(publish_module, "_check_site", _boom)

    assert run_publish().site_ok is None


def test_site_check_waits_out_the_deploy_window(monkeypatch):
    """A push triggers a deploy that takes minutes; a 404 during it isn't a failure."""
    monkeypatch.setattr(publish_module.time, "sleep", lambda _: None)
    statuses = iter([404, 404, 200])
    monkeypatch.setattr(publish_module, "_fetch_status", lambda url: next(statuses))

    publish_module._check_site("https://example.invalid/")  # must not raise


def test_site_check_gives_up_after_the_window(monkeypatch):
    monkeypatch.setattr(publish_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(publish_module, "_fetch_status", lambda url: 404)

    with pytest.raises(publish_module.PublishUnreachableError):
        publish_module._check_site("https://example.invalid/")
