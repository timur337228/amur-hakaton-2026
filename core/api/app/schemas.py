from __future__ import annotations

from datetime import date as DateType, datetime
from decimal import Decimal
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
    started_at: datetime | None = None
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


class ImportStatsResponse(BaseModel):
    batch_id: str
    date_min: DateType | None
    date_max: DateType | None
    rows_count: int
    metrics: list[str]
    source_groups: list[str]
    total_files: int
    csv_files: int
    raw_rows_imported: int
    normalized_rows_imported: int
    error_count: int


class BudgetFactPreviewRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_group: str
    source_file: str
    budget_name: str | None = None
    object_name: str | None = None
    organization_name: str | None = None
    document_number: str | None = None
    document_id: str | None = None
    date: DateType | None = None
    year: int | None = None
    month: int | None = None
    kfsr_code: str | None = None
    kcsr_code: str | None = None
    kvr_code: str | None = None
    kvsr_code: str | None = None
    kesr_code: str | None = None
    kosgu_code: str | None = None
    purpose_code: str | None = None
    funding_source: str | None = None
    metric: str
    value: Decimal


class ImportPreviewResponse(BaseModel):
    batch_id: str
    rows_count: int
    returned_rows: int
    limit: int
    offset: int
    rows: list[BudgetFactPreviewRow]


class AnalyticsFilters(BaseModel):
    source_groups: list[str] | None = None
    object_query: str | None = None
    budget_query: str | None = None
    organization_query: str | None = None
    text_search: str | None = None
    document_id: str | None = None
    document_number: str | None = None
    kfsr_code: str | None = None
    kcsr_code: str | None = None
    kvr_code: str | None = None
    kvsr_code: str | None = None
    kesr_code: str | None = None
    kosgu_code: str | None = None
    purpose_code: str | None = None
    funding_source: str | None = None


class AnalyticsQueryRequest(BaseModel):
    batch_id: str
    text_query: str | None = None
    date_from: DateType | None = None
    date_to: DateType | None = None
    metrics: list[str] | None = None
    filters: AnalyticsFilters = Field(default_factory=AnalyticsFilters)
    group_by: list[str] = Field(default_factory=lambda: ["month"])
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    include_rows: bool = True
    include_charts: bool = True


class AnalyticsExportRequest(AnalyticsQueryRequest):
    limit: int = Field(default=50000, ge=1, le=50000)
    offset: int = Field(default=0, ge=0)
    include_rows: bool = True
    include_charts: bool = True


class AnalyticsRow(BaseModel):
    dimensions: dict[str, str | int | None]
    metric: str
    value: Decimal


class AnalyticsTimeseriesPoint(BaseModel):
    period: str
    metric: str
    value: Decimal


class AnalyticsCharts(BaseModel):
    timeseries: list[AnalyticsTimeseriesPoint]
    by_metric: list[AnalyticsRow]


class AnalyticsMeta(BaseModel):
    batch_id: str
    rows_count: int
    returned_rows: int
    sources: list[str]
    metrics: list[str]
    group_by: list[str]
    date_from: DateType | None = None
    date_to: DateType | None = None
    llm_applied: bool = False
    text_query: str | None = None
    resolved_request: dict | None = None
    warning: str | None = None


class AnalyticsQueryResponse(BaseModel):
    summary: dict[str, Decimal]
    execution_percent: Decimal | None
    rows: list[AnalyticsRow]
    charts: AnalyticsCharts | None
    meta: AnalyticsMeta


class AnalyticsOptionsResponse(BaseModel):
    metrics: dict[str, str]
    source_groups: dict[str, str]
    group_by: dict[str, str]
    filter_fields: dict[str, str]


class AnalyticsValuesResponse(BaseModel):
    field: str
    values: list[str]


class AnalyticsFilterOptionsResponse(BaseModel):
    batch_id: str
    date_min: DateType | None
    date_max: DateType | None
    limit_per_field: int
    metrics: list[str]
    source_groups: list[str]
    organizations: list[str]
    objects: list[str]
    budgets: list[str]
    kfsr_codes: list[str]
    kcsr_codes: list[str]
    kvr_codes: list[str]
    kvsr_codes: list[str]
    kesr_codes: list[str]
    kosgu_codes: list[str]
    purpose_codes: list[str]
    funding_sources: list[str]
    document_numbers: list[str]
    document_ids: list[str]


class AnalyticsLLMInterpretation(BaseModel):
    date_from: DateType | None = None
    date_to: DateType | None = None
    metrics: list[str] | None = None
    filters: AnalyticsFilters = Field(default_factory=AnalyticsFilters)
    group_by: list[str] | None = None


class AnalyticsResolveTextResponse(BaseModel):
    batch_id: str
    text_query: str | None = None
    llm_applied: bool
    llm_interpretation: AnalyticsLLMInterpretation | None = None
    resolved_request: dict
    warning: str | None = None


class PreparedAnalyticsExample(BaseModel):
    prompt: str
    title: str
    resolved_request: dict
    response: AnalyticsQueryResponse


class PreparedAnalyticsExamplesResponse(BaseModel):
    batch_id: str
    examples: list[PreparedAnalyticsExample]


class AudioTranscriptWord(BaseModel):
    word: str
    start: float | None = None
    end: float | None = None


class AudioTranscriptionResponse(BaseModel):
    provider: str
    model: str
    raw_text: str
    normalized_text: str
    correction_applied: bool
    language: str | None = None
    duration_seconds: float | None = None
    words: list[AudioTranscriptWord] = Field(default_factory=list)
    warning: str | None = None
