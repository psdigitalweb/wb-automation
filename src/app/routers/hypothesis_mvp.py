"""API for global hypotheses MVP and project experiments."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db_hypotheses import (
    create_hypothesis_with_version,
    get_hypothesis_by_id,
    list_hypotheses_with_latest_version,
    update_hypothesis,
)
from app.db_hl_mvp import (
    confirm_hl_mvp_run,
    create_hl_mvp_experiment,
    get_hl_mvp_experiment,
    get_latest_result_for_experiment,
    list_hl_mvp_experiments,
    list_hl_mvp_runs,
    start_hl_mvp_experiment,
    stop_hl_mvp_experiment,
)
from app.deps import get_current_active_user, get_project_membership
from app.schemas.hypothesis_mvp import (
    ExperimentCreate,
    ExperimentDetail,
    ExperimentListItem,
    HypothesisCreate,
    HypothesisOut,
    HypothesisPatch,
    ResultItem,
    RunItem,
)


router_hypotheses = APIRouter(prefix="/api/v1", tags=["hypotheses"])
router_experiments = APIRouter(prefix="/api/v1/projects", tags=["hypothesis-mvp"])


@router_hypotheses.get("/hypotheses", response_model=List[HypothesisOut])
def get_hypotheses(
    query: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    _current_user: dict = Depends(get_current_active_user),
):
    rows = list_hypotheses_with_latest_version(query=query, limit=limit, status=status_filter)
    return [HypothesisOut(**row) for row in rows]


@router_hypotheses.get("/hypotheses/{hypothesis_id}", response_model=HypothesisOut)
def get_hypothesis_detail(
    hypothesis_id: int = Path(...),
    _current_user: dict = Depends(get_current_active_user),
):
    hypothesis = get_hypothesis_by_id(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return HypothesisOut(**hypothesis)


@router_hypotheses.post("/hypotheses", response_model=HypothesisOut, status_code=status.HTTP_201_CREATED)
def create_hypothesis(
    body: HypothesisCreate,
    _current_user: dict = Depends(get_current_active_user),
):
    try:
        row = create_hypothesis_with_version(
            key=body.key,
            title=body.title,
            description=body.description,
            domain=body.domain,
            hypothesis_type=body.hypothesis_type,
            hypothesis_text=body.hypothesis_text,
            primary_metric_key=body.primary_metric_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HypothesisOut(**row)


@router_hypotheses.patch("/hypotheses/{hypothesis_id}", response_model=HypothesisOut)
def patch_hypothesis(
    hypothesis_id: int = Path(...),
    body: HypothesisPatch = ...,
    _current_user: dict = Depends(get_current_active_user),
):
    updated = update_hypothesis(
        hypothesis_id,
        title=body.title,
        description=body.description,
        status=body.status,
        domain=body.domain,
        hypothesis_type=body.hypothesis_type,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    return HypothesisOut(**updated)


@router_experiments.get("/{project_id}/hypothesis/experiments", response_model=List[ExperimentListItem])
def list_experiments(
    project_id: int = Path(...),
    status_filter: str | None = Query(None, alias="status"),
    metric: str | None = Query(None),
    hypothesis_id: int | None = Query(None),
    nm_id: int | None = Query(None),
    query: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _member: dict = Depends(get_project_membership),
):
    rows = list_hl_mvp_experiments(
        project_id=project_id,
        status=status_filter,
        metric=metric,
        hypothesis_id=hypothesis_id,
        nm_id=nm_id,
        query=query,
        limit=limit,
    )
    return [ExperimentListItem(**row) for row in rows]


@router_experiments.post(
    "/{project_id}/hypothesis/experiments",
    response_model=ExperimentListItem,
    status_code=status.HTTP_201_CREATED,
)
def create_experiment(
    project_id: int = Path(...),
    body: ExperimentCreate = ...,
    _member: dict = Depends(get_project_membership),
):
    if not get_hypothesis_by_id(body.hypothesis_id):
        raise HTTPException(status_code=400, detail="Hypothesis not found")

    row = create_hl_mvp_experiment(
        project_id=project_id,
        hypothesis_id=body.hypothesis_id,
        nm_id=body.nm_id,
        change_type=body.change_type,
        change_note=body.change_note,
        metric=body.metric,
    )
    return ExperimentListItem(**row)


@router_experiments.get(
    "/{project_id}/hypothesis/experiments/{experiment_id}",
    response_model=ExperimentDetail,
)
def get_experiment_detail(
    project_id: int = Path(...),
    experiment_id: int = Path(...),
    _member: dict = Depends(get_project_membership),
):
    experiment = get_hl_mvp_experiment(experiment_id, project_id=project_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    runs = [RunItem(**row) for row in list_hl_mvp_runs(experiment_id)]
    latest_result = get_latest_result_for_experiment(experiment_id)
    out: Dict[str, Any] = {
        **experiment,
        "runs": runs,
        "latest_result": ResultItem(**latest_result) if latest_result else None,
    }
    return ExperimentDetail(**out)


@router_experiments.post("/{project_id}/hypothesis/experiments/{experiment_id}/start")
def start_experiment(
    project_id: int = Path(...),
    experiment_id: int = Path(...),
    _member: dict = Depends(get_project_membership),
):
    experiment = start_hl_mvp_experiment(experiment_id, project_id)
    if not experiment:
        experiment_check = get_hl_mvp_experiment(experiment_id, project_id)
        if not experiment_check:
            raise HTTPException(status_code=404, detail="Experiment not found")
        if experiment_check["status"] != "draft":
            raise HTTPException(status_code=400, detail="Experiment is not in draft status")
        raise HTTPException(status_code=409, detail="This SKU is already TEST in another active experiment")
    return experiment


@router_experiments.post("/{project_id}/hypothesis/runs/{run_id}/confirm")
def confirm_run(
    project_id: int = Path(...),
    run_id: int = Path(...),
    _member: dict = Depends(get_project_membership),
):
    if not confirm_hl_mvp_run(run_id, project_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "change_confirmed_at": "now"}


@router_experiments.post("/{project_id}/hypothesis/experiments/{experiment_id}/stop")
def stop_experiment(
    project_id: int = Path(...),
    experiment_id: int = Path(...),
    _member: dict = Depends(get_project_membership),
):
    experiment = stop_hl_mvp_experiment(experiment_id, project_id)
    if not experiment:
        experiment_check = get_hl_mvp_experiment(experiment_id, project_id)
        if not experiment_check:
            raise HTTPException(status_code=404, detail="Experiment not found")
        raise HTTPException(status_code=400, detail="Experiment is not running")
    return experiment
