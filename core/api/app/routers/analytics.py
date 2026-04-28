from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from tempfile import NamedTemporaryFile

from ..db import get_db
from ..models import ImportBatch
from ..schemas import (
    AudioTranscriptionResponse,
    AnalyticsExportRequest,
    AnalyticsFilterOptionsResponse,
    AnalyticsOptionsResponse,
    PreparedAnalyticsExamplesResponse,
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
    prepared_analytics_examples,
    resolve_analytics_text,
    run_analytics_request,
)
from ..services.speech_to_text import (
    SpeechToTextConfigurationError,
    SpeechToTextServiceError,
    SUPPORTED_AUDIO_EXTENSIONS,
    transcribe_audio_file,
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


@router.post("/transcribe-audio", response_model=AudioTranscriptionResponse)
async def transcribe_audio(
    file: Annotated[UploadFile, File(description="Audio query file")],
    batch_id: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
) -> AudioTranscriptionResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Supported extensions: {supported}.",
        )

    filter_options = None
    if batch_id:
        if not db.get(ImportBatch, batch_id):
            raise HTTPException(status_code=404, detail="Import batch not found.")
        filter_options = analytics_filter_options(db, batch_id=batch_id, limit=80)

    try:
        with NamedTemporaryFile(delete=False, suffix=suffix or ".audio") as temporary_file:
            while chunk := await file.read(1024 * 1024):
                temporary_file.write(chunk)
            temp_path = Path(temporary_file.name)
        result = transcribe_audio_file(temp_path, filter_options=filter_options)
    except SpeechToTextConfigurationError as exc:
        raise HTTPException(status_code=500, detail="Аудио выдало ошибку, попробуйте снова.") from exc
    except SpeechToTextServiceError as exc:
        raise HTTPException(status_code=502, detail="Аудио выдало ошибку, попробуйте снова.") from exc
    finally:
        await file.close()
        if "temp_path" in locals():
            temp_path.unlink(missing_ok=True)

    return AudioTranscriptionResponse(
        provider=result.provider,
        model=result.model,
        raw_text=result.raw_text,
        normalized_text=result.normalized_text,
        correction_applied=result.correction_applied,
        language=result.language,
        duration_seconds=result.duration_seconds,
        words=result.words,
        warning=result.warning,
    )


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


@router.get("/prepared-examples", response_model=PreparedAnalyticsExamplesResponse)
def get_prepared_examples(
    batch_id: str,
    db: Session = Depends(get_db),
) -> PreparedAnalyticsExamplesResponse:
    if not db.get(ImportBatch, batch_id):
        raise HTTPException(status_code=404, detail="Import batch not found.")
    try:
        return prepared_analytics_examples(db, batch_id=batch_id)
    except AnalyticsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
