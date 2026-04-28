from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

from core.api.app.services.archive import ArchiveError, extract_archive, is_supported_archive
from tests.helpers import workspace_tempdir


class ArchiveTests(unittest.TestCase):
    def test_supported_archive_extensions(self) -> None:
        self.assertTrue(is_supported_archive("dataset.zip"))
        self.assertTrue(is_supported_archive("dataset.rar"))
        self.assertTrue(is_supported_archive("dataset.7z"))
        self.assertFalse(is_supported_archive("dataset.csv"))

    def test_extract_zip_keeps_nested_files(self) -> None:
        with workspace_tempdir() as directory:
            root = Path(directory)
            archive_path = root / "dataset.zip"
            destination = root / "out"

            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("1. РЧБ/январь2025.csv", "Бюджет;Дата проводки\n")

            extract_archive(archive_path, destination)

            self.assertTrue((destination / "1. РЧБ" / "январь2025.csv").exists())

    def test_extract_zip_rejects_zip_slip_paths(self) -> None:
        with workspace_tempdir() as directory:
            root = Path(directory)
            archive_path = root / "bad.zip"

            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../evil.csv", "oops")

            with self.assertRaises(ArchiveError):
                extract_archive(archive_path, root / "out")


if __name__ == "__main__":
    unittest.main()
