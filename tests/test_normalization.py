from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from core.api.app.services.normalization import (
    detect_date_from_filename,
    normalize_code,
    normalize_header,
    parse_amount,
    parse_date,
)


class NormalizationTests(unittest.TestCase):
    def test_parse_amount_handles_russian_number_format(self) -> None:
        self.assertEqual(parse_amount("1 600 000 000,50"), Decimal("1600000000.50"))
        self.assertEqual(parse_amount("-37 206,75"), Decimal("-37206.75"))
        self.assertIsNone(parse_amount(""))

    def test_parse_date_handles_supported_formats(self) -> None:
        self.assertEqual(parse_date("01.09.2025"), date(2025, 9, 1))
        self.assertEqual(parse_date("2025-03-07 00:00:00.000"), date(2025, 3, 7))
        self.assertIsNone(parse_date("not a date"))

    def test_normalize_header_and_code(self) -> None:
        self.assertEqual(normalize_header("Подтв. лимитов по БО 2025 год"), "подтвлимитовпобо2025год")
        self.assertEqual(normalize_code("03.2.01.97002"), "0320197002")

    def test_detect_date_from_filename(self) -> None:
        self.assertEqual(detect_date_from_filename(Path("август2025.csv")), date(2025, 8, 1))
        self.assertEqual(detect_date_from_filename(Path("на01022026.csv")), date(2026, 2, 1))
        self.assertIsNone(detect_date_from_filename(Path("Контракты и договора.csv")))


if __name__ == "__main__":
    unittest.main()
