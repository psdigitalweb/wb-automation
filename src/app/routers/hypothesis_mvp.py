"""API for global hypotheses MVP."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.db_hypotheses import (
    create_hypothesis_with_version,
    get_hypothesis_by_id,
    list_hypotheses_with_latest_version,
    update_hypothesis,
)
from app.deps import get_current_active_user
from app.schemas.hypothesis_mvp import HypothesisCreate, HypothesisOut, HypothesisPatch


router_hypotheses = APIRouter(prefix="/api/v1", tags=["hypotheses"])


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
