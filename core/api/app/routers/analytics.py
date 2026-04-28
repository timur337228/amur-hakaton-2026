from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import (
    AnalyticsOptionsResponse,
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    AnalyticsValuesResponse,
)
from ..services.analytics import (
    AnalyticsValidationError,
    analytics_options,
    distinct_field_values,
    run_analytics_query,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.post("/query", response_model=AnalyticsQueryResponse)
def query_analytics(payload: AnalyticsQueryRequest, db: Session = Depends(get_db)) -> AnalyticsQueryResponse:
    try:
        return run_analytics_query(db, payload)
    except AnalyticsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/options", response_model=AnalyticsOptionsResponse)
def get_analytics_options() -> dict:
    return analytics_options()


@router.get("/values", response_model=AnalyticsValuesResponse)
def get_distinct_values(
    batch_id: str,
    field: str,
    query: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> AnalyticsValuesResponse:
    try:
        values = distinct_field_values(db, batch_id=batch_id, field=field, query=query, limit=limit)
    except AnalyticsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AnalyticsValuesResponse(field=field, values=values)
