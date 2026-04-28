from __future__ import annotations

import os
import unittest
from pathlib import Path

TEST_DB_PATH = Path.cwd() / ".test_tmp" / "import_dedup.sqlite"
TEST_DB_PATH.parent.mkdir(exist_ok=True)
os.environ["DATABASE_SYNC_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["STORAGE_DIR"] = "storage_test_import_dedup"

from core.api.app.db import Base, SessionLocal, engine  # noqa: E402
from core.api.app.models import Agreement, BudgetFact  # noqa: E402
from core.api.app.services.importer import ImportService  # noqa: E402
from tests.helpers import workspace_tempdir  # noqa: E402


class ImportDedupTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def test_import_deduplicates_repeated_agreement_snapshots(self) -> None:
        content = (
            "period_of_date,documentclass_id,budget_id,caption,document_id,close_date,reg_number,"
            "main_close_date,main_reg_number,amount_1year,dd_estimate_caption,dd_recipient_caption,"
            "kadmr_code,kfsr_code,kcsr_code,kvr_code,dd_purposefulgrant_code,kesr_code,kdr_code,kde_code,kdf_code,dd_grantinvestment_code\n"
            "2025-01-01 - 2026-04-01,273,1,Областной бюджет,1211004645445,2026-01-28 00:00:00.000,637,"
            "2025-08-20 00:00:00.000,637,102402899.00,,ГАУ Амурской области \"\"Авиабаза\"\","
            "928,0408,1320211010,462,0,000,983,000,000,\n"
        )

        with workspace_tempdir() as directory:
            root = Path(directory) / "dataset" / "2. Соглашения"
            root.mkdir(parents=True)
            (root / "на01022026.csv").write_text(content, encoding="utf-8-sig")
            (root / "на01032026.csv").write_text(content, encoding="utf-8-sig")

            with SessionLocal() as db:
                batch = ImportService(db).import_local_path(root.parent, original_name="agreements-dataset")
                agreements_count = db.query(Agreement).filter(Agreement.batch_id == batch.id).count()
                facts = db.query(BudgetFact).filter(BudgetFact.batch_id == batch.id).all()

        self.assertEqual(batch.status, "completed")
        self.assertEqual(agreements_count, 1)
        self.assertEqual(len(facts), 1)
        self.assertEqual(str(facts[0].value), "102402899.00")
        self.assertEqual(facts[0].metric, "agreement_amount")


if __name__ == "__main__":
    unittest.main()
