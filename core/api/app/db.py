from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autoflush=False, autocommit=False, future=True)
SessionLocal.configure(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def configure_database(database_url: str | None = None):
    global engine

    new_engine = create_engine(database_url or settings.database_url, pool_pre_ping=True, future=True)
    try:
        engine.dispose()
    except Exception:
        pass
    engine = new_engine
    SessionLocal.configure(bind=engine)
    return engine


def run_migrations(database_url: str | None = None) -> None:
    if database_url:
        configure_database(database_url)
    project_root = Path(__file__).resolve().parents[3]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url or settings.database_url)
    command.upgrade(alembic_config, "head")
