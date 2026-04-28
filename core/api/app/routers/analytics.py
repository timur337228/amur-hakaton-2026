from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ImportBatch
from ..schemas import (
    AnalyticsExportRequest,
    AnalyticsFilterOptionsResponse,
    AnalyticsOptionsResponse,
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    AnalyticsResolveTextResponse,
    AnalyticsValuesResponse,
)
from ..services.analytics import (
    AnalyticsValidationError,
    analytics_filter_options,
    analytics_options,
    distinct_field_values,
    resolve_analytics_text,
    run_analytics_request,
)
from ..services.xlsx_export import XLSX_MEDIA_TYPE, build_analytics_xlsx

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.post("/query", response_model=AnalyticsQueryResponse)
def query_analytics(payload: AnalyticsQueryRequest, db: Session = Depends(get_db)) -> AnalyticsQueryResponse:
    try:
        return run_analytics_request(db, payload)
    except AnalyticsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/resolve-text", response_model=AnalyticsResolveTextResponse)
def resolve_text(payload: AnalyticsQueryRequest, db: Session = Depends(get_db)) -> AnalyticsResolveTextResponse:
    try:
        return resolve_analytics_text(db, payload)
    except AnalyticsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/export/xlsx")
def export_analytics_xlsx(payload: AnalyticsExportRequest, db: Session = Depends(get_db)) -> Response:
    try:
        query_payload = payload.model_copy(update={"include_rows": True, "include_charts": True})
        result = run_analytics_request(db, query_payload)
    except AnalyticsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    content = build_analytics_xlsx(result)
    filename = _export_filename(payload.batch_id)
    disposition = f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )


@router.get("/options", response_model=AnalyticsOptionsResponse)
def get_analytics_options() -> dict:
    return analytics_options()


@router.get("/filter-options", response_model=AnalyticsFilterOptionsResponse)
def get_filter_options(
    batch_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> AnalyticsFilterOptionsResponse:
    if not db.get(ImportBatch, batch_id):
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return analytics_filter_options(db, batch_id=batch_id, limit=limit)


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


def _export_filename(batch_id: str) -> str:
    safe_batch_id = "".join(char for char in batch_id if char.isalnum() or char in "-_")[:36] or "batch"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"analytics_{safe_batch_id}_{timestamp}.xlsx"
