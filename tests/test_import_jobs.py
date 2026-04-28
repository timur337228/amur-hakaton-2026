from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

TEST_DB_PATH = Path.cwd() / ".test_tmp" / "import_jobs_test.sqlite"
TEST_DB_PATH.parent.mkdir(exist_ok=True)
os.environ["DATABASE_SYNC_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["STORAGE_DIR"] = "storage_test_jobs"

from core.api.app.db import SessionLocal, run_migrations  # noqa: E402
from core.api.app.models import BudgetFact, ImportBatch  # noqa: E402
from core.api.app.services.import_jobs import ImportJobRunner  # noqa: E402
from core.api.app.services.importer import ImportService  # noqa: E402
from tests.helpers import workspace_tempdir  # noqa: E402


class ImportJobRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_DB_PATH.unlink(missing_ok=True)
        run_migrations(database_url=f"sqlite+pysqlite:///{TEST_DB_PATH.as_posix()}")

    def test_background_local_path_job_completes_and_updates_batch(self) -> None:
        runner = ImportJobRunner()

        with workspace_tempdir() as directory:
            root = Path(directory)
            source = root / "dataset" / "1. РЧБ"
            source.mkdir(parents=True)
            (source / "январь2025.csv").write_text(
                "\n".join(
                    [
                        "министерство финансов Амурской области;;;;;;;;;;;;;;;;;;;;;",
                        "Бюджет;Дата проводки;КФСР;Наименование КФСР;КЦСР;Наименование КЦСР;КВР;Наименование КВР;КВСР;Наименование КВСР;КОСГУ;Наименование КОСГУ;Код цели;Наименование Код цели;КВФО;Наименование КВФО;Источник средств;Лимиты ПБС 2025 год;Подтв. лимитов по БО 2025 год;Подтв. лимитов без БО 2025 год;Остаток лимитов 2025 год;Всего выбытий (бух.уч.)",
                        "Бюджет города;01.01.2025;05.02;Коммунальное хозяйство;03.2.01.61058;Мероприятие;8.1.2;Субсидии;002;Администрация;0.0.0;НЕ УКАЗАНО;ОБ-1;Код цели;1;Бюджетная деятельность;Региональные средства;100,00;50,00;0,00;50,00;25,00",
                    ]
                ),
                encoding="utf-8-sig",
            )

            with SessionLocal() as db:
                service = ImportService(db)
                batch = service.create_batch(input_type="local_path", original_name="test-dataset")
                service.mark_batch_queued(batch, "Queued local path import.")

            runner.enqueue_local_path(batch.id, root / "dataset")
            final_status = self._wait_for_batch_status(batch.id, {"completed", "completed_with_errors", "failed"})
            runner.stop()

            with SessionLocal() as db:
                refreshed_batch = db.get(ImportBatch, batch.id)
                facts_count = db.query(BudgetFact).filter(BudgetFact.batch_id == batch.id).count()

        self.assertEqual(final_status, "completed")
        self.assertIsNotNone(refreshed_batch)
        self.assertEqual(refreshed_batch.status, "completed")
        self.assertGreater(facts_count, 0)

    def _wait_for_batch_status(self, batch_id: str, terminal_statuses: set[str], timeout: float = 10.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with SessionLocal() as db:
                batch = db.get(ImportBatch, batch_id)
                if batch and batch.status in terminal_statuses:
                    return batch.status
            time.sleep(0.1)
        self.fail(f"Timed out waiting for batch {batch_id} to reach {sorted(terminal_statuses)}")


if __name__ == "__main__":
    unittest.main()
