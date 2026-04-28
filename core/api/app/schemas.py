from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    status: str
    input_type: str
    original_name: str | None = None
    total_files: int
    csv_files: int
    raw_rows_imported: int
    normalized_rows_imported: int
    error_count: int
    message: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class LocalImportRequest(BaseModel):
    path: str = Field(default="project_file", description="Path relative to project root, e.g. project_file")


class RawFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    relative_path: str
    source_group: str
    extension: str
    status: str
    rows_count: int
    raw_rows_imported: int
    normalized_rows_imported: int
    error_message: str | None = None


class ImportFilesResponse(BaseModel):
    batch_id: str
    files: list[RawFileResponse]


class ImportErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    raw_file_id: int | None
    level: str
    message: str
    context: dict | None = None
    created_at: datetime | None = None
