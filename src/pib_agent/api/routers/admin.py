import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pib_agent.api.deps import SessionScopeFn, get_db, get_session_scope
from pib_agent.api.mapping import to_pipeline_run_out
from pib_agent.api.schemas import PaginatedPipelineRuns, PipelineRunOut
from pib_agent.config import get_settings
from pib_agent.db.models import PipelineRun
from pib_agent.orchestration import (
    PipelineAlreadyRunningError,
    execute_pipeline_run,
    start_pipeline_run,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-now", response_model=PipelineRunOut, status_code=202)
def run_now(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    session_scope: SessionScopeFn = Depends(get_session_scope),
) -> PipelineRunOut:
    """Kick off scrape -> enrich -> link -> notify immediately and return right away.

    The run executes in the background; poll GET /admin/runs/{id} (the id in
    this response) for its final status. Rejects with 429 if a manual run was
    started too recently, or 409 if a run (scheduled or manual) is already
    in progress.
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.admin_run_now_min_interval_seconds)
    recent = (
        session.query(PipelineRun)
        .filter(PipelineRun.trigger == "manual", PipelineRun.started_at >= cutoff)
        .order_by(PipelineRun.started_at.desc())
        .first()
    )
    if recent is not None:
        raise HTTPException(
            status_code=429, detail="Triggered too recently; wait before retrying."
        )

    try:
        run_id = start_pipeline_run("manual", session_scope=session_scope)
    except PipelineAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    background_tasks.add_task(execute_pipeline_run, run_id, session_scope=session_scope)

    run = session.get(PipelineRun, run_id)
    return to_pipeline_run_out(run)


@router.get("/runs", response_model=PaginatedPipelineRuns)
def list_runs(
    session: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedPipelineRuns:
    query = session.query(PipelineRun)
    total = query.count()
    rows = query.order_by(PipelineRun.started_at.desc()).offset(offset).limit(limit).all()
    return PaginatedPipelineRuns(
        items=[to_pipeline_run_out(run) for run in rows], total=total, limit=limit, offset=offset
    )


@router.get("/runs/{run_id}", response_model=PipelineRunOut)
def get_run(run_id: int, session: Session = Depends(get_db)) -> PipelineRunOut:
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return to_pipeline_run_out(run)
