from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import BudgetFact
from ..schemas import (
    AnalyticsCharts,
    AnalyticsFilterOptionsResponse,
    AnalyticsMeta,
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    AnalyticsRow,
    AnalyticsTimeseriesPoint,
)


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
