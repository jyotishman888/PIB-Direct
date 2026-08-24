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
