from __future__ import annotations

import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

TEST_DB_PATH = Path.cwd() / ".test_tmp" / "analytics_test.sqlite"
TEST_DB_PATH.parent.mkdir(exist_ok=True)
os.environ["DATABASE_SYNC_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["STORAGE_DIR"] = "storage_test"

from core.api.app.db import Base, SessionLocal, engine  # noqa: E402
from core.api.app.models import BudgetFact, ImportBatch  # noqa: E402
from core.api.app.schemas import AnalyticsFilters, AnalyticsQueryRequest  # noqa: E402
from core.api.app.services.analytics import distinct_field_values, run_analytics_query  # noqa: E402


class AnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            db.add(ImportBatch(id="batch-1", input_type="test", status="completed"))
            db.add_all(
                [
                    _fact(
                        metric="limits",
                        value=Decimal("100.00"),
                        date_value=date(2025, 1, 10),
                        object_name="Бюджет города Благовещенска",
                        kfsr_code="0502",
                    ),
                    _fact(
                        metric="limits",
                        value=Decimal("200.00"),
                        date_value=date(2025, 2, 10),
                        object_name="Бюджет города Благовещенска",
                        kfsr_code="0502",
                    ),
                    _fact(
                        metric="cash_payments",
                        value=Decimal("50.00"),
                        date_value=date(2025, 1, 20),
                        object_name="Бюджет города Благовещенска",
                        kfsr_code="0502",
                    ),
                    _fact(
                        metric="cash_payments",
                        value=Decimal("999.00"),
                        date_value=date(2025, 1, 20),
                        object_name="Бюджет города Свободного",
                        kfsr_code="0502",
                    ),
                    _fact(
                        metric="contract_amount",
                        value=Decimal("500.00"),
                        date_value=date(2025, 3, 1),
                        object_name="1401000010706",
                        source_group="gz",
                        document_number="Ф.2025.0003",
                    ),
                ]
            )
            db.commit()

    def test_query_filters_and_groups_by_month(self) -> None:
        request = AnalyticsQueryRequest(
            batch_id="batch-1",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            metrics=["limits", "cash_payments"],
            filters=AnalyticsFilters(object_query="Благовещенск"),
            group_by=["month"],
        )

        with SessionLocal() as db:
            response = run_analytics_query(db, request)

        self.assertEqual(response.summary["limits"], Decimal("300.00"))
        self.assertEqual(response.summary["cash_payments"], Decimal("50.00"))
        self.assertEqual(response.execution_percent, Decimal("16.67"))
        self.assertEqual(response.meta.sources, ["rchb"])
        self.assertEqual(response.meta.rows_count, 3)
        self.assertTrue(all("year" in row.dimensions and "month" in row.dimensions for row in response.rows))
        self.assertEqual(
            {(point.period, point.metric, point.value) for point in response.charts.timeseries},
            {
                ("2025-01", "cash_payments", Decimal("50.00")),
                ("2025-01", "limits", Decimal("100.00")),
                ("2025-02", "limits", Decimal("200.00")),
            },
        )

    def test_query_supports_exact_code_filter(self) -> None:
        request = AnalyticsQueryRequest(
            batch_id="batch-1",
            metrics=["cash_payments"],
            filters=AnalyticsFilters(kfsr_code="0502", object_query="Свободного"),
            group_by=["object_name"],
        )

        with SessionLocal() as db:
            response = run_analytics_query(db, request)

        self.assertEqual(response.summary["cash_payments"], Decimal("999.00"))
        self.assertEqual(response.rows[0].dimensions["object_name"], "Бюджет города Свободного")

    def test_distinct_values_search(self) -> None:
        with SessionLocal() as db:
            values = distinct_field_values(db, batch_id="batch-1", field="object_name", query="Благо", limit=10)

        self.assertEqual(values, ["Бюджет города Благовещенска"])


def _fact(
    *,
    metric: str,
    value: Decimal,
    date_value: date,
    object_name: str,
    source_group: str = "rchb",
    kfsr_code: str | None = None,
    document_number: str | None = None,
) -> BudgetFact:
    return BudgetFact(
        batch_id="batch-1",
        raw_file_id=1,
        source_group=source_group,
        source_file="test.csv",
        budget_name=object_name,
        object_name=object_name,
        organization_name="Администрация",
        document_number=document_number,
        date=date_value,
        year=date_value.year,
        month=date_value.month,
        kfsr_code=kfsr_code,
        metric=metric,
        value=value,
        raw_data={},
    )


if __name__ == "__main__":
    unittest.main()
