from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from ..schemas import AnalyticsQueryResponse


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_analytics_xlsx(response: AnalyticsQueryResponse) -> bytes:
    sheets = [
        ("Summary", _summary_rows(response)),
        ("Data", _data_rows(response)),
        ("ChartsData", _charts_rows(response)),
    ]
    return _build_workbook(sheets)


def _summary_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    meta = response.meta
    rows: list[list[Any]] = [
        ["Report", "Analytics export"],
        ["Batch ID", meta.batch_id],
        ["Date from", meta.date_from],
        ["Date to", meta.date_to],
        ["Sources", ", ".join(meta.sources)],
        ["Metrics", ", ".join(meta.metrics)],
        ["Group by", ", ".join(meta.group_by)],
        ["Rows count", meta.rows_count],
        ["Returned rows", meta.returned_rows],
        ["Execution percent", response.execution_percent],
        [],
        ["Metric", "Value"],
    ]
    rows.extend([metric, value] for metric, value in response.summary.items())
    return rows


def _data_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    dimension_keys = _dimension_keys(response)
    rows: list[list[Any]] = [dimension_keys + ["metric", "value"]]
    for row in response.rows:
        rows.append([row.dimensions.get(key) for key in dimension_keys] + [row.metric, row.value])
    return rows


def _charts_rows(response: AnalyticsQueryResponse) -> list[list[Any]]:
    rows: list[list[Any]] = [["Timeseries"], ["period", "metric", "value"]]
    if response.charts:
        rows.extend([point.period, point.metric, point.value] for point in response.charts.timeseries)
        rows.extend([[], ["By metric"], ["metric", "value"]])
        rows.extend([row.metric, row.value] for row in response.charts.by_metric)
    return rows


def _dimension_keys(response: AnalyticsQueryResponse) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in response.rows:
        for key in row.dimensions:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


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
    cols = "\n".join(f'<col min="{index}" max="{index}" width="18" customWidth="1"/>' for index in range(1, max_col + 1))
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
