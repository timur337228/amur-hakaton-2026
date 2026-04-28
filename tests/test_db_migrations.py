from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from tests.helpers import workspace_tempdir


class DatabaseMigrationTests(unittest.TestCase):
    def test_run_migrations_creates_expected_tables(self) -> None:
        from core.api.app.db import run_migrations

        with workspace_tempdir() as directory:
            db_path = Path(directory) / "migrations.sqlite"
            database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

            run_migrations(database_url=database_url)

            inspector = inspect(create_engine(database_url, future=True))
            table_names = set(inspector.get_table_names())

        self.assertIn("alembic_version", table_names)
        self.assertIn("import_batches", table_names)
        self.assertIn("raw_files", table_names)
        self.assertIn("budget_facts", table_names)
        self.assertIn("agreements", table_names)
        self.assertIn("contracts", table_names)
        self.assertIn("payments", table_names)

    def test_run_migrations_stamps_legacy_schema_created_before_alembic(self) -> None:
        from core.api.app import db as db_module
        from core.api.app.db import Base, run_migrations
        from core.api.app import models  # noqa: F401

        with workspace_tempdir() as directory:
            db_path = Path(directory) / "legacy.sqlite"
            database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

            legacy_engine = db_module.configure_database(database_url)
            Base.metadata.create_all(bind=legacy_engine)

            run_migrations(database_url=database_url)

            inspector = inspect(create_engine(database_url, future=True))
            table_names = set(inspector.get_table_names())

            with create_engine(database_url, future=True).connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

        self.assertIn("alembic_version", table_names)
        self.assertEqual(revision, "20260428_0001")


if __name__ == "__main__":
    unittest.main()
