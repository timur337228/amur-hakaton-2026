from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter(include_in_schema=False)


def site_root() -> Path:
    return Path(__file__).resolve().parents[3] / "site"


def site_index_path() -> Path:
    return site_root() / "index.html"


@router.get("/")
def index() -> FileResponse:
    return FileResponse(site_index_path())
