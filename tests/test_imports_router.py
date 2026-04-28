from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from core.api.app.routers.imports import import_local_path, upload_archive, upload_files  # noqa: E402
from core.api.app.schemas import LocalImportRequest  # noqa: E402


class ImportsRouterTests(unittest.TestCase):
    def test_archive_upload_is_blocked_in_deploy_mode(self) -> None:
        upload = _AsyncUploadStub(filename="dataset.zip", content=b"zip")

        with patch(
            "core.api.app.routers.imports.get_settings",
            return_value=SimpleNamespace(deploy_mode=True, allow_local_import=True, project_root=Path.cwd()),
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(upload_archive(upload, db=SimpleNamespace()))

        self.assertEqual(error.exception.status_code, 403)

    def test_files_upload_is_blocked_in_deploy_mode(self) -> None:
        upload = _AsyncUploadStub(filename="part.csv", content=b"csv")

        with patch(
            "core.api.app.routers.imports.get_settings",
            return_value=SimpleNamespace(deploy_mode=True, allow_local_import=True, project_root=Path.cwd()),
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(upload_files([upload], ["1. РЧБ/part.csv"], db=SimpleNamespace()))

        self.assertEqual(error.exception.status_code, 403)

    def test_local_path_import_is_blocked_in_deploy_mode(self) -> None:
        with patch(
            "core.api.app.routers.imports.get_settings",
            return_value=SimpleNamespace(deploy_mode=True, allow_local_import=True, project_root=Path.cwd()),
        ):
            with self.assertRaises(HTTPException) as error:
                import_local_path(LocalImportRequest(path="project_file"), db=SimpleNamespace())

        self.assertEqual(error.exception.status_code, 403)


class _AsyncUploadStub:
    def __init__(self, *, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content
        self._read = False

    async def read(self, size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._content

    async def close(self) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
