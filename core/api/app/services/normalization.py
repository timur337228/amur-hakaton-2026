from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


MONTHS_RU = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\ufeff", "").strip()
    return text or None


def normalize_header(value: str) -> str:
    value = value.replace("\ufeff", "").lower().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", "", value)
    return value


def normalize_code(value: object) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace(" ", "").replace(".", "")
    return text or None


def parse_amount(value: object) -> Decimal | None:
    text = clean_text(value)
    if not text:
        return None

    text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in {"", "-", ".", "-."}:
        return None

    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: object) -> date | None:
    text = clean_text(value)
    if not text:
        return None

    text = text.split(" ")[0]
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def date_parts(value: date | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    return value.year, value.month


def detect_date_from_filename(path: Path) -> date | None:
    name = path.stem.lower().replace("ё", "е")

    compact = re.search(r"на(\d{2})(\d{2})(\d{4})", name)
    if compact:
        day, month, year = compact.groups()
        return date(int(year), int(month), int(day))

    year_match = re.search(r"(20\d{2})", name)
    if not year_match:
        return None
    year = int(year_match.group(1))

    for month_prefix, month in MONTHS_RU.items():
        if month_prefix in name:
            return date(year, month, 1)
    return None
