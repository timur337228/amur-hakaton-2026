from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _sync_database_url() -> str:
    sync_url = os.getenv("DATABASE_SYNC_URL")
    if sync_url:
        return sync_url

    url = os.getenv("DATABASE_URL")
    if not url:
        return "postgresql+psycopg://budget_app:budget_app_dev@localhost:5432/budget_analytics"

    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


@dataclass(frozen=True)
class Settings:
    project_root: Path
    storage_dir: Path
    database_url: str
    allow_local_import: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    _load_env_file(project_root / ".env")

    storage_dir = Path(os.getenv("STORAGE_DIR", "storage"))
    if not storage_dir.is_absolute():
        storage_dir = project_root / storage_dir

    return Settings(
        project_root=project_root,
        storage_dir=storage_dir,
        database_url=_sync_database_url(),
        allow_local_import=os.getenv("ALLOW_LOCAL_IMPORT", "true").lower() in {"1", "true", "yes", "on"},
    )
