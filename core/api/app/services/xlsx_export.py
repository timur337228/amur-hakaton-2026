from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from .analytics import GROUP_BY_LABELS, METRIC_LABELS, SOURCE_GROUP_LABELS
from ..schemas import AnalyticsQueryResponse, AnalyticsRow


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

OBJECT_HEADERS = [
    "Объект / мероприятие",
    "Период",
    "План / лимиты",
    "Бюджетные обязательства",
    "Кассовые выплаты",
    "Соглашения",
    "Контракты / договоры",
    "Платежи по контрактам",
    "Остаток лимитов",
    "Исполнение, %",
    "Итого по строке",
]

OBJECT_METRIC_COLUMNS = [
    ("limits", "План / лимиты"),
    ("obligations", "Бюджетные обязательства"),
    ("cash_payments", "Кассовые выплаты"),
    ("agreement_amount", "Соглашения"),
    ("contract_amount", "Контракты / договоры"),
    ("contract_payment", "Платежи по контрактам"),
    ("remaining_limits", "Остаток лимитов"),
]


def build_analytics_xlsx(response: AnalyticsQueryResponse) -> bytes:
    sheets = [
        ("Параметры", _parameter_rows(response)),
        ("Сводка по объектам", _object_summary_rows(response)),
        ("Итоги по объектам", _object_totals_rows(response)),
        ("Динамика", _dynamics_rows(response)),
        ("Детализация", _detail_rows(response)),
    ]
    return _build_workbook(sheets)


def _parameter_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    meta = response.meta
    request = meta.resolved_request or {}
    filters = request.get("filters") or {}
    rows: list[list[Any]] = [
        ["Отчёт", "Бюджетная аналитика"],
        ["Текстовый запрос", meta.text_query or ""],
        ["Пакет данных", meta.batch_id],
        ["Период отчёта", _meta_period_label(response)],
        ["Источники", ", ".join(SOURCE_GROUP_LABELS.get(source, source) for source in meta.sources)],
        ["Показатели", ", ".join(METRIC_LABELS.get(metric, metric) for metric in meta.metrics)],
        ["Группировка интерфейса", ", ".join(GROUP_BY_LABELS.get(item, item) for item in meta.group_by)],
        ["Объект", filters.get("object_query") or ""],
        ["Организация", filters.get("organization_query") or ""],
        ["Бюджет", filters.get("budget_query") or ""],
        ["КФСР", filters.get("kfsr_code") or ""],
        ["КЦСР", filters.get("kcsr_code") or ""],
        ["КВР", filters.get("kvr_code") or ""],
        ["Источник средств", filters.get("funding_source") or ""],
        ["Строк в результате", meta.rows_count],
        ["Строк в выгрузке", meta.returned_rows],
        ["Исполнение, %", response.execution_percent],
        [],
        ["Итоговый показатель", "Значение"],
    ]
    rows.extend([METRIC_LABELS.get(metric, metric), value] for metric, value in response.summary.items())
    return rows


def _object_summary_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    buckets = _group_rows_by_object_and_period(response)
    rows: list[list[Any]] = [OBJECT_HEADERS]
    for (object_name, period), metrics in buckets.items():
        rows.append(_object_summary_row(object_name, period, metrics))
    if len(rows) == 1:
        rows.append(["Нет данных", "", None, None, None, None, None, None, None, None, None])
    return rows


def _object_totals_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    buckets = _group_rows_by_object_and_period(response)
    totals: dict[str, dict[str, Decimal]] = {}
    for (object_name, _period), metrics in buckets.items():
        object_totals = totals.setdefault(object_name, {})
        for metric, value in metrics.items():
            object_totals[metric] = object_totals.get(metric, Decimal("0.00")) + value

    rows: list[list[Any]] = [OBJECT_HEADERS]
    for object_name, metrics in totals.items():
        rows.append(_object_summary_row(object_name, "Итого", metrics))
    if len(rows) == 1:
        rows.append(["Нет данных", "", None, None, None, None, None, None, None, None, None])
    return rows


def _dynamics_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    rows: list[list[Any]] = [["Объект / мероприятие", "Период", "Показатель", "Значение"]]
    for row in response.rows:
        rows.append(
            [
                _object_name_for_row(row, response),
                _period_for_row(row, response),
                METRIC_LABELS.get(row.metric, row.metric),
                row.value,
            ]
        )
    if len(rows) == 1:
        rows.append(["Нет данных", "", "", None])
    return rows


def _detail_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    dimension_keys = _dimension_keys(response)
    headers = [_dimension_label(key) for key in dimension_keys] + ["Показатель", "Значение"]
    rows: list[list[Any]] = [headers]
    for row in response.rows:
        rows.append(
            [row.dimensions.get(key) for key in dimension_keys]
            + [METRIC_LABELS.get(row.metric, row.metric), row.value]
        )
    if len(rows) == 1:
        rows.append(["Нет данных"] + [""] * (len(headers) - 1))
    return rows


def _group_rows_by_object_and_period(response: AnalyticsQueryResponse) -> dict[tuple[str, str], dict[str, Decimal]]:
    buckets: dict[tuple[str, str], dict[str, Decimal]] = {}
    for row in response.rows:
        key = (_object_name_for_row(row, response), _period_for_row(row, response))
        metric_bucket = buckets.setdefault(key, {})
        metric_bucket[row.metric] = metric_bucket.get(row.metric, Decimal("0.00")) + row.value
    return dict(sorted(buckets.items(), key=lambda item: (item[0][0], item[0][1])))


def _object_summary_row(object_name: str, period: str, metrics: dict[str, Decimal]) -> list[Any]:
    values = [metrics.get(metric) for metric, _label in OBJECT_METRIC_COLUMNS]
    limits = metrics.get("limits")
    cash = metrics.get("cash_payments")
    execution_percent = None
    if limits not in {None, Decimal("0.00")} and cash is not None:
        execution_percent = ((cash / limits) * Decimal("100")).quantize(Decimal("0.01"))
    total_value = sum((value for value in values if isinstance(value, Decimal)), Decimal("0.00"))
    return [object_name, period, *values, execution_percent, total_value]


def _object_name_for_row(row: AnalyticsRow, response: AnalyticsQueryResponse) -> str:
    object_name = row.dimensions.get("object_name")
    if object_name:
        return str(object_name)
    request = response.meta.resolved_request or {}
    filters = request.get("filters") or {}
    if filters.get("object_query"):
        return str(filters["object_query"])
    return "Все объекты"


def _period_for_row(row: AnalyticsRow, response: AnalyticsQueryResponse) -> str:
    dimensions = row.dimensions
    if dimensions.get("day"):
        return str(dimensions["day"])
    year = dimensions.get("year")
    month = dimensions.get("month")
    if year and month:
        return f"{int(year):04d}-{int(month):02d}"
    if year:
        return str(year)
    return _meta_period_label(response)


def _meta_period_label(response: AnalyticsQueryResponse) -> str:
    date_from = response.meta.date_from.isoformat() if response.meta.date_from else "—"
    date_to = response.meta.date_to.isoformat() if response.meta.date_to else "—"
    return f"{date_from} — {date_to}"


def _dimension_keys(response: AnalyticsQueryResponse) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in response.rows:
        for key in row.dimensions:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def _dimension_label(key: str) -> str:
    if key in {"year", "month", "day"}:
        return GROUP_BY_LABELS.get(key, key)
    return GROUP_BY_LABELS.get(key, key.replace("_", " ").title())


def _build_workbook(sheets: list[tuple[str, list[list[Any]]]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types(len(sheets)))
        zf.writestr("_rels/.rels", _root_rels())
        zf.writestr("docProps/core.xml", _core_properties())
        zf.writestr("docProps/app.xml", _app_properties(sheets))
        zf.writestr("xl/workbook.xml", _workbook(sheets))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheets)))
        zf.writestr("xl/styles.xml", _styles())
        for index, (_, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet(rows))
    return output.getvalue()


def _content_types(sheet_count: int) -> str:
    sheet_overrides = "\n".join(
        (
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        for index in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheet_overrides}
</Types>"""


def _root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _core_properties() -> str:
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:creator>budget-analytics-api</dc:creator>
<cp:lastModifiedBy>budget-analytics-api</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{created_at}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{created_at}</dcterms:modified>
</cp:coreProperties>"""


def _app_properties(sheets: list[tuple[str, list[list[Any]]]]) -> str:
    sheet_names = "".join(f"<vt:lpstr>{_xml_escape(name)}</vt:lpstr>" for name, _ in sheets)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>budget-analytics-api</Application>
<TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">{sheet_names}</vt:vector></TitlesOfParts>
</Properties>"""


def _workbook(sheets: list[tuple[str, list[list[Any]]]]) -> str:
    sheet_items = "\n".join(
        f'<sheet name="{_xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheet_items}
</sheets>
</workbook>"""


def _workbook_rels(sheet_count: int) -> str:
    sheet_rels = "\n".join(
        (
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
        for index in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{sheet_rels}
<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
</styleSheet>"""


def _worksheet(rows: list[list[Any]]) -> str:
    sheet_rows = "\n".join(_row_xml(index, row) for index, row in enumerate(rows, start=1))
    max_col = max((len(row) for row in rows), default=1)
    cols = "\n".join(f'<col min="{index}" max="{index}" width="22" customWidth="1"/>' for index in range(1, max_col + 1))
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0"/></sheetViews>
<sheetFormatPr defaultRowHeight="15"/>
<cols>
{cols}
</cols>
<sheetData>
{sheet_rows}
</sheetData>
</worksheet>"""


def _row_xml(row_index: int, row: list[Any]) -> str:
    cells = "".join(_cell_xml(row_index, col_index, value, is_header=row_index == 1) for col_index, value in enumerate(row, start=1))
    return f'<row r="{row_index}">{cells}</row>'


def _cell_xml(row_index: int, col_index: int, value: Any, *, is_header: bool) -> str:
    reference = f"{_column_name(col_index)}{row_index}"
    style = ' s="1"' if is_header else ""
    if value is None:
        return f'<c r="{reference}"{style}/>'
    if isinstance(value, Decimal):
        return f'<c r="{reference}"{style}><v>{value}</v></c>'
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"{style}><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{reference}"{style}><v>{value}</v></c>'
    if isinstance(value, date):
        value = value.isoformat()
    return f'<c r="{reference}" t="inlineStr"{style}><is><t>{_xml_escape(str(value))}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xml_escape(value: str) -> str:
    cleaned = "".join(char for char in value if char in "\t\n\r" or ord(char) >= 32)
    return (
        cleaned.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
