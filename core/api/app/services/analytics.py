from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session

from ..models import BudgetFact
from ..schemas import (
    AnalyticsCharts,
    AnalyticsFilterOptionsResponse,
    AnalyticsFilters,
    AnalyticsLLMInterpretation,
    AnalyticsMeta,
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    AnalyticsResolveTextResponse,
    AnalyticsRow,
    AnalyticsTimeseriesPoint,
    PreparedAnalyticsExample,
    PreparedAnalyticsExamplesResponse,
)
from .llm import LLMConfigurationError, LLMServiceError, resolve_text_query_to_request_patch


METRIC_LABELS = {
    "limits": "Лимиты",
    "obligations": "Подтв. лимитов по БО",
    "obligations_without_bo": "Подтв. лимитов без БО",
    "remaining_limits": "Остаток лимитов",
    "cash_payments": "Кассовые выплаты",
    "agreement_amount": "Сумма соглашений",
    "contract_amount": "Сумма контрактов",
    "contract_payment": "Платежи по контрактам",
    "institution_payments_with_refund": "Выплаты БУАУ с учетом возврата",
    "institution_payments_execution": "Выплаты БУАУ - исполнение",
    "institution_payments_recovery": "Восстановление выплат БУАУ",
}

SOURCE_GROUP_LABELS = {
    "rchb": "РЧБ",
    "agreements": "Соглашения",
    "gz": "Госзаказ",
    "buau": "БУАУ",
}

GROUP_BY_LABELS = {
    "day": "День",
    "month": "Месяц",
    "year": "Год",
    "budget_name": "Бюджет",
    "object_name": "Объект",
    "organization_name": "Организация",
    "source_group": "Источник",
    "metric": "Показатель",
    "kfsr_code": "КФСР",
    "kcsr_code": "КЦСР",
    "kvr_code": "КВР",
    "kvsr_code": "КВСР",
    "kesr_code": "КОСГУ/КЭСР",
    "kosgu_code": "КОСГУ",
    "purpose_code": "Код цели",
    "funding_source": "Источник средств",
}

FILTER_FIELD_LABELS = {
    "source_groups": "Источники данных",
    "object_query": "Поиск по объекту",
    "budget_query": "Поиск по бюджету",
    "organization_query": "Поиск по организации",
    "text_search": "Текстовый поиск",
    "document_id": "ID документа",
    "document_number": "Номер документа",
    "kfsr_code": "КФСР",
    "kcsr_code": "КЦСР",
    "kvr_code": "КВР",
    "kvsr_code": "КВСР",
    "kesr_code": "КОСГУ/КЭСР",
    "kosgu_code": "КОСГУ",
    "purpose_code": "Код цели",
    "funding_source": "Источник средств",
}

DISTINCT_VALUE_FIELDS = {
    "budget_name": BudgetFact.budget_name,
    "object_name": BudgetFact.object_name,
    "organization_name": BudgetFact.organization_name,
    "source_group": BudgetFact.source_group,
    "metric": BudgetFact.metric,
    "kfsr_code": BudgetFact.kfsr_code,
    "kcsr_code": BudgetFact.kcsr_code,
    "kvr_code": BudgetFact.kvr_code,
    "kvsr_code": BudgetFact.kvsr_code,
    "kesr_code": BudgetFact.kesr_code,
    "kosgu_code": BudgetFact.kosgu_code,
    "purpose_code": BudgetFact.purpose_code,
    "funding_source": BudgetFact.funding_source,
    "document_number": BudgetFact.document_number,
    "document_id": BudgetFact.document_id,
}

FILTER_OPTION_FIELDS = {
    "metrics": BudgetFact.metric,
    "source_groups": BudgetFact.source_group,
    "organizations": BudgetFact.organization_name,
    "objects": BudgetFact.object_name,
    "budgets": BudgetFact.budget_name,
    "kfsr_codes": BudgetFact.kfsr_code,
    "kcsr_codes": BudgetFact.kcsr_code,
    "kvr_codes": BudgetFact.kvr_code,
    "kvsr_codes": BudgetFact.kvsr_code,
    "kesr_codes": BudgetFact.kesr_code,
    "kosgu_codes": BudgetFact.kosgu_code,
    "purpose_codes": BudgetFact.purpose_code,
    "funding_sources": BudgetFact.funding_source,
    "document_numbers": BudgetFact.document_number,
    "document_ids": BudgetFact.document_id,
}
_PREPARED_EXAMPLES_CACHE: dict[str, PreparedAnalyticsExamplesResponse] = {}

TEXT_SEARCH_COLUMNS = (
    BudgetFact.object_name,
    BudgetFact.budget_name,
    BudgetFact.organization_name,
    BudgetFact.funding_source,
    BudgetFact.document_number,
    BudgetFact.document_id,
    BudgetFact.kfsr_code,
    BudgetFact.kcsr_code,
    BudgetFact.kvr_code,
    BudgetFact.kvsr_code,
    BudgetFact.kesr_code,
    BudgetFact.kosgu_code,
    BudgetFact.purpose_code,
    BudgetFact.source_file,
    cast(BudgetFact.raw_data, Text),
)

TEXT_SEARCH_STOPWORDS = {
    "а",
    "был",
    "была",
    "были",
    "было",
    "в",
    "во",
    "выплат",
    "выплата",
    "выплаты",
    "где",
    "год",
    "года",
    "годам",
    "году",
    "данные",
    "для",
    "до",
    "за",
    "из",
    "и",
    "или",
    "источник",
    "источникам",
    "источники",
    "источнику",
    "итого",
    "как",
    "какая",
    "какие",
    "какой",
    "кассовые",
    "кассовых",
    "контракт",
    "контрактам",
    "контрактов",
    "лимит",
    "лимиты",
    "месяц",
    "месяцам",
    "на",
    "об",
    "от",
    "по",
    "покажи",
    "показать",
    "получено",
    "потрачен",
    "потрачено",
    "потраченные",
    "потратили",
    "оплат",
    "оплата",
    "платеж",
    "платежи",
    "про",
    "договор",
    "договоров",
    "обязательства",
    "остаток",
    "нибудь",
    "расход",
    "расходы",
    "сколько",
    "средств",
    "сумма",
    "суммарно",
    "суммы",
    "соглашений",
    "соглашения",
    "тема",
    "теме",
    "темой",
    "тему",
    "траты",
    "что",
    "это",
}

TEXT_METRIC_HINTS = {
    "cash_payments": ("кассов", "выбыти", "расход", "потра", "трат"),
    "limits": ("лимит",),
    "agreement_amount": ("соглаш",),
    "contract_amount": ("контракт", "договор"),
    "contract_payment": ("платеж", "оплат"),
    "obligations_without_bo": ("без бо",),
    "obligations": ("обязатель", "бо"),
    "remaining_limits": ("остаток лимит",),
}

PREPARED_EXAMPLE_SPECS = (
    (
        "Покажи лимиты по Благовещенску по месяцам",
        "Лимиты по Благовещенску",
        {
            "metrics": ["limits"],
            "filters": {"object_query": "Благовещенск"},
            "group_by": ["month"],
        },
    ),
    (
        "Покажи кассовые выплаты по 0502",
        "Кассовые выплаты по 0502",
        {
            "metrics": ["cash_payments"],
            "filters": {"kfsr_code": "0502"},
            "group_by": ["month"],
        },
    ),
    (
        "Покажи сумму контрактов по источнику gz",
        "Контракты по gz",
        {
            "metrics": ["contract_amount"],
            "filters": {"source_groups": ["gz"]},
            "group_by": ["month"],
        },
    ),
)


class AnalyticsValidationError(ValueError):
    pass


def run_analytics_query(db: Session, request: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
    group_by = _validate_group_by(request.group_by)
    metrics = _validate_metrics(request.metrics)

    base_conditions = _build_conditions(request, metrics)

    summary = _summary(db, base_conditions)
    rows, rows_count = _rows(db, base_conditions, group_by, request.limit, request.offset) if request.include_rows else ([], 0)
    charts = _charts(db, base_conditions) if request.include_charts else None
    sources = _distinct_values(db, BudgetFact.source_group, base_conditions)
    response_metrics = sorted(summary.keys())

    return AnalyticsQueryResponse(
        summary=summary,
        execution_percent=_execution_percent(summary),
        rows=rows,
        charts=charts,
        meta=AnalyticsMeta(
            batch_id=request.batch_id,
            rows_count=rows_count,
            returned_rows=len(rows),
            sources=sources,
            metrics=response_metrics,
            group_by=group_by,
            date_from=request.date_from,
            date_to=request.date_to,
        ),
    )


def run_analytics_request(db: Session, request: AnalyticsQueryRequest) -> AnalyticsQueryResponse:
    resolved_request, llm_patch, llm_applied, warning = resolve_analytics_request_details(db, request)
    response = run_analytics_query(db, resolved_request)
    response.meta.llm_applied = llm_applied
    response.meta.text_query = _normalize_optional_text(request.text_query)
    response.meta.resolved_request = _serialize_resolved_request(resolved_request)
    response.meta.warning = warning
    return response


def resolve_analytics_request(db: Session, request: AnalyticsQueryRequest) -> tuple[AnalyticsQueryRequest, bool]:
    resolved_request, _, llm_applied, _ = resolve_analytics_request_details(db, request)
    return resolved_request, llm_applied


def resolve_analytics_text(db: Session, request: AnalyticsQueryRequest) -> AnalyticsResolveTextResponse:
    resolved_request, llm_patch, llm_applied, warning = resolve_analytics_request_details(db, request)
    return AnalyticsResolveTextResponse(
        batch_id=request.batch_id,
        text_query=_normalize_optional_text(request.text_query),
        llm_applied=llm_applied,
        llm_interpretation=llm_patch,
        resolved_request=_serialize_resolved_request(resolved_request),
        warning=warning,
    )


def resolve_analytics_request_details(
    db: Session,
    request: AnalyticsQueryRequest,
) -> tuple[AnalyticsQueryRequest, AnalyticsLLMInterpretation | None, bool, str | None]:
    text_query = _normalize_optional_text(request.text_query)
    llm_patch = None
    warning = None
    if text_query:
        filter_options = analytics_filter_options(db, batch_id=request.batch_id, limit=50)
        try:
            llm_patch = resolve_text_query_to_request_patch(
                text_query=text_query,
                filter_options=filter_options,
            )
        except (LLMConfigurationError, LLMServiceError) as exc:
            warning = (
                "LLM временно недоступен. Текстовый запрос не был интерпретирован, "
                "поэтому использованы только ручные фильтры."
            )
            explicit_request = request.model_copy(update={"text_query": text_query})
            resolved_request = _merge_request_with_patch(explicit_request, None)
            resolved_request = _apply_text_query_safety(resolved_request)
            return resolved_request, None, False, f"{warning} Причина: {exc}"

    normalized_request = request.model_copy(update={"text_query": text_query})
    resolved_request = _merge_request_with_patch(normalized_request, llm_patch)
    resolved_request = _apply_text_query_safety(resolved_request)
    return resolved_request, llm_patch, llm_patch is not None, warning


def distinct_field_values(
    db: Session,
    batch_id: str,
    field: str,
    query: str | None = None,
    limit: int = 50,
) -> list[str]:
    column = DISTINCT_VALUE_FIELDS.get(field)
    if column is None:
        raise AnalyticsValidationError(f"Unsupported values field: {field}")

    stmt = (
        select(column)
        .where(BudgetFact.batch_id == batch_id, column.is_not(None), column != "")
        .distinct()
        .order_by(column)
        .limit(limit)
    )
    if query:
        stmt = stmt.where(column.ilike(f"%{query}%"))

    return [str(value) for value in db.execute(stmt).scalars().all()]


def analytics_options() -> dict:
    return {
        "metrics": METRIC_LABELS,
        "source_groups": SOURCE_GROUP_LABELS,
        "group_by": GROUP_BY_LABELS,
        "filter_fields": FILTER_FIELD_LABELS,
    }


def analytics_filter_options(db: Session, batch_id: str, limit: int = 200) -> AnalyticsFilterOptionsResponse:
    date_min, date_max = db.execute(
        select(func.min(BudgetFact.date), func.max(BudgetFact.date)).where(BudgetFact.batch_id == batch_id)
    ).one()
    values = {
        field_name: _distinct_values(db, column, [BudgetFact.batch_id == batch_id], limit=limit)
        for field_name, column in FILTER_OPTION_FIELDS.items()
    }

    return AnalyticsFilterOptionsResponse(
        batch_id=batch_id,
        date_min=date_min,
        date_max=date_max,
        limit_per_field=limit,
        **values,
    )


def prepared_analytics_examples(db: Session, batch_id: str) -> PreparedAnalyticsExamplesResponse:
    cached = _PREPARED_EXAMPLES_CACHE.get(batch_id)
    if cached is not None:
        return cached.model_copy(deep=True)

    examples: list[PreparedAnalyticsExample] = []
    for prompt, title, payload in PREPARED_EXAMPLE_SPECS:
        request = AnalyticsQueryRequest.model_validate(
            {
                "batch_id": batch_id,
                "text_query": prompt,
                "include_rows": True,
                "include_charts": True,
                **payload,
            }
        )
        response = run_analytics_query(db, request)
        response.meta.llm_applied = False
        response.meta.text_query = prompt
        response.meta.resolved_request = _serialize_resolved_request(request)
        response.meta.warning = None
        examples.append(
            PreparedAnalyticsExample(
                prompt=prompt,
                title=title,
                resolved_request=_serialize_resolved_request(request),
                response=response,
            )
        )
    response = PreparedAnalyticsExamplesResponse(batch_id=batch_id, examples=examples)
    _PREPARED_EXAMPLES_CACHE[batch_id] = response.model_copy(deep=True)
    return response


def _apply_text_query_safety(request: AnalyticsQueryRequest) -> AnalyticsQueryRequest:
    text_query = _normalize_optional_text(request.text_query)
    if not text_query:
        return request

    update_data: dict[str, object] = {}
    if request.date_from is None and request.date_to is None:
        year_range = _infer_single_year_range(text_query)
        if year_range:
            update_data["date_from"], update_data["date_to"] = year_range

    if not request.metrics:
        inferred_metric = _infer_metric_from_query_text(text_query)
        if inferred_metric:
            update_data["metrics"] = [inferred_metric]

    filters = request.filters
    if not _has_subject_filter(filters):
        terms = _extract_text_search_terms(text_query)
        if terms:
            update_data["filters"] = filters.model_copy(update={"text_search": " ".join(terms)})

    if not update_data:
        return request
    return request.model_copy(update=update_data)


def _build_conditions(request: AnalyticsQueryRequest, metrics: list[str] | None) -> list:
    filters = request.filters
    conditions = [BudgetFact.batch_id == request.batch_id]

    if request.date_from:
        conditions.append(BudgetFact.date >= request.date_from)
    if request.date_to:
        conditions.append(BudgetFact.date <= request.date_to)
    if metrics:
        conditions.append(BudgetFact.metric.in_(metrics))
    if filters.source_groups:
        conditions.append(BudgetFact.source_group.in_(filters.source_groups))
    if filters.object_query:
        like = f"%{filters.object_query}%"
        conditions.append(or_(BudgetFact.object_name.ilike(like), BudgetFact.budget_name.ilike(like)))
    if filters.budget_query:
        conditions.append(BudgetFact.budget_name.ilike(f"%{filters.budget_query}%"))
    if filters.organization_query:
        conditions.append(BudgetFact.organization_name.ilike(f"%{filters.organization_query}%"))
    if filters.text_search:
        conditions.extend(_text_search_conditions(filters.text_search))

    exact_filters = {
        "document_id": BudgetFact.document_id,
        "document_number": BudgetFact.document_number,
        "kfsr_code": BudgetFact.kfsr_code,
        "kcsr_code": BudgetFact.kcsr_code,
        "kvr_code": BudgetFact.kvr_code,
        "kvsr_code": BudgetFact.kvsr_code,
        "kesr_code": BudgetFact.kesr_code,
        "kosgu_code": BudgetFact.kosgu_code,
        "purpose_code": BudgetFact.purpose_code,
        "funding_source": BudgetFact.funding_source,
    }
    for field_name, column in exact_filters.items():
        value = getattr(filters, field_name)
        if value:
            conditions.append(column == value)

    return conditions


def _text_search_conditions(text_search: str) -> list:
    terms = _extract_text_search_terms(text_search)
    conditions = []
    for term in terms:
        likes = [f"%{variant}%" for variant in _text_search_term_variants(term)]
        conditions.append(or_(*(column.ilike(like) for column in TEXT_SEARCH_COLUMNS for like in likes)))
    return conditions


def _text_search_term_variants(term: str) -> list[str]:
    variants = [term, term.capitalize(), term.upper()]
    result: list[str] = []
    for variant in variants:
        if variant not in result:
            result.append(variant)
    return result


def _has_subject_filter(filters: AnalyticsFilters) -> bool:
    return any(
        getattr(filters, field_name)
        for field_name in (
            "object_query",
            "budget_query",
            "organization_query",
            "text_search",
            "document_id",
            "document_number",
            "kfsr_code",
            "kcsr_code",
            "kvr_code",
            "kvsr_code",
            "kesr_code",
            "kosgu_code",
            "purpose_code",
            "funding_source",
        )
    )


def _infer_single_year_range(text_query: str) -> tuple[date, date] | None:
    years = {int(match) for match in re.findall(r"\b(19\d{2}|20\d{2})\b", text_query)}
    if len(years) != 1:
        return None
    year = years.pop()
    return date(year, 1, 1), date(year, 12, 31)


def _infer_metric_from_query_text(text_query: str) -> str | None:
    lowered = _normalize_search_text(text_query)
    for metric, hints in TEXT_METRIC_HINTS.items():
        if any(hint in lowered for hint in hints):
            return metric if metric in METRIC_LABELS else None
    return None


def _extract_text_search_terms(text_query: str) -> list[str]:
    terms: list[str] = []
    for raw_term in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text_query):
        term = _normalize_search_text(raw_term)
        if not term or len(term) < 3:
            continue
        if term.isdigit() or any(char.isdigit() for char in term):
            continue
        if term in TEXT_SEARCH_STOPWORDS:
            continue
        stemmed = _stem_text_search_term(term)
        if len(stemmed) < 3 or stemmed in TEXT_SEARCH_STOPWORDS:
            continue
        if stemmed not in terms:
            terms.append(stemmed)
    return terms


def _stem_text_search_term(term: str) -> str:
    suffixes = (
        "иями",
        "ями",
        "ами",
        "ого",
        "ему",
        "ыми",
        "ими",
        "ской",
        "скому",
        "ские",
        "ский",
        "ская",
        "ское",
        "ого",
        "его",
        "ому",
        "ему",
        "ой",
        "ей",
        "ая",
        "яя",
        "ое",
        "ее",
        "ые",
        "ие",
        "ом",
        "ем",
        "ам",
        "ям",
        "ах",
        "ях",
        "ов",
        "ев",
        "ий",
        "ый",
        "ую",
        "юю",
        "а",
        "я",
        "ы",
        "и",
        "у",
        "ю",
        "е",
        "о",
    )
    for suffix in suffixes:
        if term.endswith(suffix) and len(term) - len(suffix) >= 4:
            return term[: -len(suffix)]
    return term


def _normalize_search_text(value: str) -> str:
    return value.lower().replace("ё", "е").strip()


def _merge_request_with_patch(
    request: AnalyticsQueryRequest,
    patch: AnalyticsLLMInterpretation | None,
) -> AnalyticsQueryRequest:
    resolved = AnalyticsQueryRequest(batch_id=request.batch_id)
    if patch is not None:
        patch_data = patch.model_dump(exclude_none=True)
        resolved = AnalyticsQueryRequest.model_validate(
            {
                **resolved.model_dump(mode="python"),
                **patch_data,
                "batch_id": request.batch_id,
            }
        )

    explicit_fields = set(request.model_fields_set)
    if "text_query" in explicit_fields:
        explicit_fields.remove("text_query")

    update_data: dict[str, object] = {}
    for field_name in explicit_fields:
        if field_name == "filters":
            continue
        value = getattr(request, field_name)
        if value is None:
            continue
        update_data[field_name] = value
    if update_data:
        resolved = resolved.model_copy(update=update_data)

    merged_filters = dict(resolved.filters.model_dump(exclude_none=True))
    explicit_filter_fields = set(request.filters.model_fields_set)
    for field_name in explicit_filter_fields:
        value = getattr(request.filters, field_name)
        if value is not None:
            merged_filters[field_name] = value
    resolved_filters = AnalyticsFilters.model_validate(merged_filters)

    return resolved.model_copy(
        update={
            "batch_id": request.batch_id,
            "text_query": request.text_query,
            "filters": resolved_filters,
        }
    )


def _summary(db: Session, conditions: list) -> dict[str, Decimal]:
    stmt = (
        select(BudgetFact.metric, func.coalesce(func.sum(BudgetFact.value), 0))
        .where(*conditions)
        .group_by(BudgetFact.metric)
    )
    return {metric: _to_decimal(value) for metric, value in db.execute(stmt).all()}


def _rows(
    db: Session,
    conditions: list,
    group_by: list[str],
    limit: int,
    offset: int,
) -> tuple[list[AnalyticsRow], int]:
    group_pairs = _group_pairs(group_by)
    columns = [column for _, column in group_pairs]
    select_columns = [column.label(label) for label, column in group_pairs]

    group_columns = columns + [BudgetFact.metric]
    stmt = (
        select(*select_columns, BudgetFact.metric.label("metric"), func.coalesce(func.sum(BudgetFact.value), 0).label("value"))
        .where(*conditions)
        .group_by(*group_columns)
        .order_by(*group_columns)
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    rows_count = int(db.execute(count_stmt).scalar_one())

    rows = []
    for row in db.execute(stmt.limit(limit).offset(offset)).mappings().all():
        dimensions = {label: row.get(label) for label, _ in group_pairs}
        if "metric" in group_by:
            dimensions["metric"] = row["metric"]
        rows.append(
            AnalyticsRow(
                dimensions=dimensions,
                metric=row["metric"],
                value=_to_decimal(row["value"]),
            )
        )
    return rows, rows_count


def _charts(db: Session, conditions: list) -> AnalyticsCharts:
    by_metric = [
        AnalyticsRow(dimensions={"metric": metric}, metric=metric, value=value)
        for metric, value in _summary(db, conditions).items()
    ]

    stmt = (
        select(
            BudgetFact.year,
            BudgetFact.month,
            BudgetFact.metric,
            func.coalesce(func.sum(BudgetFact.value), 0).label("value"),
        )
        .where(*conditions, BudgetFact.year.is_not(None), BudgetFact.month.is_not(None))
        .group_by(BudgetFact.year, BudgetFact.month, BudgetFact.metric)
        .order_by(BudgetFact.year, BudgetFact.month, BudgetFact.metric)
    )
    timeseries = [
        AnalyticsTimeseriesPoint(
            period=f"{int(year):04d}-{int(month):02d}",
            metric=metric,
            value=_to_decimal(value),
        )
        for year, month, metric, value in db.execute(stmt).all()
    ]

    return AnalyticsCharts(timeseries=timeseries, by_metric=by_metric)


def _distinct_values(db: Session, column, conditions: list, limit: int | None = None) -> list[str]:
    stmt = select(column).where(*conditions, column.is_not(None), column != "").distinct().order_by(column)
    if limit is not None:
        stmt = stmt.limit(limit)
    return [str(value) for value in db.execute(stmt).scalars().all()]


def _serialize_resolved_request(request: AnalyticsQueryRequest) -> dict[str, object]:
    return request.model_dump(exclude={"text_query"}, exclude_none=True, mode="json")


def _group_pairs(group_by: list[str]) -> list[tuple[str, object]]:
    pairs: list[tuple[str, object]] = []
    seen: set[str] = set()
    for field in group_by:
        if field == "metric":
            continue
        if field == "day":
            _append_pair(pairs, seen, "day", BudgetFact.date)
        elif field == "month":
            _append_pair(pairs, seen, "year", BudgetFact.year)
            _append_pair(pairs, seen, "month", BudgetFact.month)
        elif field == "year":
            _append_pair(pairs, seen, "year", BudgetFact.year)
        else:
            column = DISTINCT_VALUE_FIELDS.get(field)
            if column is None:
                raise AnalyticsValidationError(f"Unsupported group_by field: {field}")
            _append_pair(pairs, seen, field, column)
    return pairs


def _append_pair(pairs: list[tuple[str, object]], seen: set[str], label: str, column: object) -> None:
    if label in seen:
        return
    seen.add(label)
    pairs.append((label, column))


def _validate_group_by(group_by: list[str]) -> list[str]:
    if not group_by:
        return ["month"]
    unsupported = [field for field in group_by if field not in GROUP_BY_LABELS]
    if unsupported:
        raise AnalyticsValidationError(f"Unsupported group_by field(s): {', '.join(unsupported)}")
    return group_by


def _validate_metrics(metrics: list[str] | None) -> list[str] | None:
    if not metrics:
        return None
    unsupported = [metric for metric in metrics if metric not in METRIC_LABELS]
    if unsupported:
        raise AnalyticsValidationError(f"Unsupported metric(s): {', '.join(unsupported)}")
    return metrics


def _execution_percent(summary: dict[str, Decimal]) -> Decimal | None:
    limits = summary.get("limits")
    cash = summary.get("cash_payments")
    if not limits or limits == Decimal("0"):
        return None
    if cash is None:
        return None
    return ((cash / limits) * Decimal("100")).quantize(Decimal("0.01"))


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"))
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
