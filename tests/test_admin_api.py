from datetime import UTC, datetime

import pib_agent.api.routers.admin as admin_module
import pib_agent.orchestration.pipeline as pipeline_module
from pib_agent.db.models import PipelineRun
from pib_agent.enrichment.pipeline import EnrichStats
from pib_agent.orchestration import PipelineAlreadyRunningError
from pib_agent.publish import PublishStats
from pib_agent.scraper.pipeline import ScrapeStats
from pib_agent.similarity.pipeline import SimilarityStats
from pib_agent.study.pipeline import StudyStats
from pib_agent.telegram.notify import NotifyStats


def _patch_stages_noop(monkeypatch):
    monkeypatch.setattr(pipeline_module, "run_scrape", lambda: ScrapeStats())
    monkeypatch.setattr(pipeline_module, "run_enrich", lambda: EnrichStats())
    monkeypatch.setattr(pipeline_module, "run_similarity", lambda: SimilarityStats())
    monkeypatch.setattr(pipeline_module, "run_notify", lambda: NotifyStats())
    monkeypatch.setattr(pipeline_module, "run_study", lambda: StudyStats())
    # stubbed explicitly: the real stage would git-push if the operator has
    # PUBLISH_ENABLED set in their .env.
    monkeypatch.setattr(
        pipeline_module,
        "run_publish",
        lambda: PublishStats(articles=0, changed=False, pushed=False),
    )


def test_run_now_returns_202_and_completes_in_background(api_client, monkeypatch):
    client, _ = api_client
    _patch_stages_noop(monkeypatch)

    response = client.post("/api/admin/run-now")

    assert response.status_code == 202
    body = response.json()
    assert body["trigger"] == "manual"
    assert body["status"] == "running"
    run_id = body["id"]

    detail = client.get(f"/api/admin/runs/{run_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == "success"
    assert [s["name"] for s in detail_body["stages"]] == [
        "scrape",
        "enrich",
        "notify",
        "link",
        "study",
        "publish",
    ]


def test_run_now_rate_limited_on_rapid_retrigger(api_client, monkeypatch):
    client, _ = api_client
    _patch_stages_noop(monkeypatch)

    first = client.post("/api/admin/run-now")
    assert first.status_code == 202

    second = client.post("/api/admin/run-now")
    assert second.status_code == 429


def test_run_now_conflicts_when_a_run_is_already_in_progress(api_client, monkeypatch):
    client, _ = api_client

    def _raise_already_running(*args, **kwargs):
        raise PipelineAlreadyRunningError("A pipeline run is already in progress.")

    monkeypatch.setattr(admin_module, "start_pipeline_run", _raise_already_running)

    response = client.post("/api/admin/run-now")

    assert response.status_code == 409


def test_get_run_404_for_unknown_id(api_client):
    client, _ = api_client

    response = client.get("/api/admin/runs/999999")

    assert response.status_code == 404


def test_list_runs_orders_newest_first(api_client, monkeypatch):
    client, session_scope_factory = api_client
    _patch_stages_noop(monkeypatch)

    with session_scope_factory() as session:
        session.add(
            PipelineRun(
                trigger="scheduled",
                status="success",
                started_at=datetime(2020, 1, 1, tzinfo=UTC),
                finished_at=datetime(2020, 1, 1, tzinfo=UTC),
                stages=[],
            )
        )

    triggered = client.post("/api/admin/run-now")
    assert triggered.status_code == 202
    manual_run_id = triggered.json()["id"]

    listing = client.get("/api/admin/runs")

    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 2
    assert body["items"][0]["id"] == manual_run_id
