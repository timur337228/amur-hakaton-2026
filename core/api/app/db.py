from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
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
    active_engine = configure_database(database_url or settings.database_url)
    project_root = Path(__file__).resolve().parents[3]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", database_url or settings.database_url)
    _stamp_legacy_schema_if_needed(alembic_config, active_engine)
    command.upgrade(alembic_config, "head")


def _stamp_legacy_schema_if_needed(alembic_config: Config, active_engine) -> None:
    # Import models so SQLAlchemy metadata contains the full expected schema.
    from . import models  # noqa: F401

    inspector = inspect(active_engine)
    table_names = set(inspector.get_table_names())
    if "alembic_version" in table_names:
        return

    expected_tables = set(Base.metadata.tables.keys())
    existing_expected_tables = expected_tables & table_names
    if not existing_expected_tables:
        return

    missing_tables = expected_tables - table_names
    if missing_tables:
        missing_preview = ", ".join(sorted(missing_tables)[:6])
        raise RuntimeError(
            "Database contains a pre-Alembic schema, but it is incomplete. "
            f"Missing tables: {missing_preview}. "
            "Reset the database volume or finish migration manually before startup."
        )

    command.stamp(alembic_config, "head")
