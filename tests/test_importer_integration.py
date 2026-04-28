from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from tests.helpers import workspace_tempdir


@unittest.skipUnless(importlib.util.find_spec("psycopg"), "psycopg is not installed")
class ImporterIntegrationTests(unittest.TestCase):
    def test_import_local_path_smoke(self) -> None:
        from core.api.app.db import SessionLocal, init_db
        from core.api.app.models import BudgetFact
        from core.api.app.services.importer import ImportService

        init_db()

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
                batch = ImportService(db).import_local_path(root / "dataset", original_name="test-dataset")
                facts_count = db.query(BudgetFact).filter(BudgetFact.batch_id == batch.id).count()

        self.assertEqual(batch.status, "completed")
        self.assertGreater(facts_count, 0)


if __name__ == "__main__":
    unittest.main()
