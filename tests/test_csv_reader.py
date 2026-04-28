from __future__ import annotations

import unittest
from pathlib import Path

from core.api.app.services.csv_reader import find_header_row, read_csv
from tests.helpers import workspace_tempdir


class CsvReaderTests(unittest.TestCase):
    def test_read_csv_detects_utf8_and_semicolon(self) -> None:
        with workspace_tempdir() as directory:
            path = Path(directory) / "sample.csv"
            path.write_text("Бюджет;Дата проводки\nБюджет города;01.01.2025\n", encoding="utf-8-sig")

            data = read_csv(path)

            self.assertEqual(data.delimiter, ";")
            self.assertIn(data.encoding, {"utf-8-sig", "utf-8"})
            self.assertEqual(data.rows[0], ["Бюджет", "Дата проводки"])

    def test_read_csv_detects_cp1251(self) -> None:
        with workspace_tempdir() as directory:
            path = Path(directory) / "sample.csv"
            path.write_text("Бюджет;Дата проводки\nБюджет города;01.01.2025\n", encoding="cp1251")

            data = read_csv(path)

            self.assertEqual(data.encoding, "cp1251")
            self.assertEqual(data.rows[1][0], "Бюджет города")

    def test_find_header_row_skips_report_preamble(self) -> None:
        rows = [
            ["министерство финансов Амурской области"],
            [""],
            ["на 01.09.2025 г."],
            ["Бюджет", "Дата проводки", "КФСР"],
            ["Бюджет города", "01.01.2025", "0502"],
        ]

        self.assertEqual(find_header_row(rows, "rchb"), 3)
        self.assertEqual(find_header_row(rows[3:], "agreements"), 0)


if __name__ == "__main__":
    unittest.main()
