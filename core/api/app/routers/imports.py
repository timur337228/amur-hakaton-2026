from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import ImportBatch, ImportErrorLog, RawFile
from ..schemas import (
    ImportBatchResponse,
    ImportErrorResponse,
    ImportFilesResponse,
    LocalImportRequest,
    RawFileResponse,
)
from ..services.archive import ArchiveError, is_supported_archive
from ..services.importer import ImportService

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])


@router.post("/archive", response_model=ImportBatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_archive(
    file: Annotated[UploadFile, File(description="ZIP, RAR or 7Z archive with project folders")],
    db: Session = Depends(get_db),
) -> ImportBatchResponse:
    if not file.filename or not is_supported_archive(file.filename):
        raise HTTPException(status_code=400, detail="Upload .zip, .rar or .7z archive.")

    service = ImportService(db)
    batch = service.create_batch(input_type="archive", original_name=file.filename)
    upload_dir = service.upload_dir(batch.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    archive_path = upload_dir / _safe_name(file.filename)

    await _save_upload(file, archive_path)

    try:
        return _batch_response(service.import_archive(batch, archive_path))
    except ArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/files", response_model=ImportBatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_files(
    files: Annotated[list[UploadFile], File(description="Multiple files from a folder upload")],
    relative_paths: Annotated[list[str] | None, Form(description="Relative paths matching uploaded files")] = None,
    db: Session = Depends(get_db),
) -> ImportBatchResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    if relative_paths and len(relative_paths) != len(files):
        raise HTTPException(status_code=400, detail="relative_paths count must match files count.")

    service = ImportService(db)
    batch = service.create_batch(input_type="files", original_name="multipart-files")
    extracted_dir = service.extracted_dir(batch.id)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    for index, upload in enumerate(files):
        relative_path = relative_paths[index] if relative_paths else upload.filename or f"file_{index}"
        target_path = _safe_target(extracted_dir, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await _save_upload(upload, target_path)

    return _batch_response(service.process_directory(batch, extracted_dir))


@router.post("/local-path", response_model=ImportBatchResponse, status_code=status.HTTP_201_CREATED)
def import_local_path(payload: LocalImportRequest, db: Session = Depends(get_db)) -> ImportBatchResponse:
    settings = get_settings()
    if not settings.allow_local_import:
        raise HTTPException(status_code=403, detail="Local path import is disabled.")

    source_path = (settings.project_root / payload.path).resolve()
    if not _is_relative_to(source_path, settings.project_root.resolve()):
        raise HTTPException(status_code=400, detail="Path must be inside project root.")
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {payload.path}")

    service = ImportService(db)
    return _batch_response(service.import_local_path(source_path, original_name=payload.path))


@router.get("/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(batch_id: str, db: Session = Depends(get_db)) -> ImportBatchResponse:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return _batch_response(batch)


@router.get("/{batch_id}/files", response_model=ImportFilesResponse)
def get_import_files(batch_id: str, db: Session = Depends(get_db)) -> ImportFilesResponse:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found.")

    files = db.execute(
        select(RawFile).where(RawFile.batch_id == batch_id).order_by(RawFile.relative_path)
    ).scalars()
    return ImportFilesResponse(batch_id=batch_id, files=[RawFileResponse.model_validate(file, from_attributes=True) for file in files])


@router.get("/{batch_id}/errors", response_model=list[ImportErrorResponse])
def get_import_errors(batch_id: str, db: Session = Depends(get_db)) -> list[ImportErrorResponse]:
    if not db.get(ImportBatch, batch_id):
        raise HTTPException(status_code=404, detail="Import batch not found.")

    errors = db.execute(
        select(ImportErrorLog).where(ImportErrorLog.batch_id == batch_id).order_by(ImportErrorLog.created_at)
    ).scalars()
    return [ImportErrorResponse.model_validate(error, from_attributes=True) for error in errors]


async def _save_upload(upload: UploadFile, target_path: Path) -> None:
    with target_path.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            output.write(chunk)
    await upload.close()


def _safe_name(filename: str) -> str:
    return Path(filename.replace("\\", "/")).name


def _safe_target(root: Path, relative_path: str) -> Path:
    clean_relative = relative_path.replace("\\", "/").lstrip("/")
    target = (root / clean_relative).resolve()
    if not _is_relative_to(target, root.resolve()):
        raise HTTPException(status_code=400, detail=f"Unsafe relative path: {relative_path}")
    return target


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _batch_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        batch_id=batch.id,
        status=batch.status,
        input_type=batch.input_type,
        original_name=batch.original_name,
        total_files=batch.total_files,
        csv_files=batch.csv_files,
        raw_rows_imported=batch.raw_rows_imported,
        normalized_rows_imported=batch.normalized_rows_imported,
        error_count=batch.error_count,
        message=batch.message,
        created_at=batch.created_at,
        finished_at=batch.finished_at,
    )
