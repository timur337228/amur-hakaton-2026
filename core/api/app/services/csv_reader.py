from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .normalization import normalize_header


@dataclass(frozen=True)
class CsvData:
    rows: list[list[str]]
    encoding: str
    delimiter: str


def read_csv(path: Path) -> CsvData:
    raw = path.read_bytes()
    text, encoding = _decode(raw)
    delimiter = _detect_delimiter(text)
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    return CsvData(rows=rows, encoding=encoding, delimiter=delimiter)


def find_header_row(rows: list[list[str]], source_group: str) -> int:
    if source_group in {"agreements", "gz"}:
        return 0

    required = {"бюджет", "датапроводки"}
    for index, row in enumerate(rows[:80]):
        normalized = {normalize_header(cell) for cell in row}
        if required.issubset(normalized):
            return index

    # Fallback: pick the first row with many non-empty cells.
    for index, row in enumerate(rows[:80]):
        if sum(1 for cell in row if cell.strip()) >= 5:
            return index

    return 0


def row_to_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for index, header in enumerate(headers):
        header = header.strip() or f"column_{index + 1}"
        data[header] = row[index].strip() if index < len(row) else ""
    return data


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"

    candidates: list[tuple[int, str, str]] = []
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        candidates.append((_score_text(text), text, encoding))

    if candidates:
        _, text, encoding = max(candidates, key=lambda item: item[0])
        return text, encoding

    return raw.decode("latin1", errors="replace"), "latin1"


def _score_text(text: str) -> int:
    cyrillic = sum(("А" <= char <= "я") or char in "Ёё" for char in text[:20000])
    replacements = text[:20000].count("�")
    mojibake = text[:20000].count("Ð") + text[:20000].count("Ñ")
    return cyrillic * 3 - replacements * 10 - mojibake


def _detect_delimiter(text: str) -> str:
    sample = text[:10000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        counts = {";": sample.count(";"), ",": sample.count(","), "\t": sample.count("\t")}
        return max(counts, key=counts.get)
