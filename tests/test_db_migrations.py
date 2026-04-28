from __future__ import annotations

import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect

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


if __name__ == "__main__":
    unittest.main()
