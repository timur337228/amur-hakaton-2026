from __future__ import annotations

import os
import unittest

from core.api.app.schemas import AnalyticsFilterOptionsResponse
from core.api.app.services.llm import resolve_text_query_to_request_patch


def _has_live_llm_config() -> bool:
    key_names = ("LLM_API_KEY", "OPENAI_API_KEY", "THREE_ZERO_TWO_API_KEY", "API_KEY_302AI")
    has_key = any(os.getenv(name) for name in key_names)
    return os.getenv("RUN_LIVE_LLM_TESTS", "").lower() in {"1", "true", "yes", "on"} and has_key


@unittest.skipUnless(_has_live_llm_config(), "Live LLM tests require RUN_LIVE_LLM_TESTS=true and an API key")
class LiveLLMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter_options = AnalyticsFilterOptionsResponse(
            batch_id="live-test-batch",
            date_min="2025-01-01",
            date_max="2026-04-02",
            limit_per_field=50,
            metrics=["limits", "cash_payments", "contract_amount"],
            source_groups=["rchb", "gz"],
            organizations=["Администрация"],
            objects=["Бюджет города Благовещенска", "Бюджет города Свободного"],
            budgets=["Бюджет города Благовещенска", "Бюджет города Свободного"],
            kfsr_codes=["0502"],
            kcsr_codes=["03.2.01.61058"],
            kvr_codes=["8.1.2"],
            kvsr_codes=["002"],
            kesr_codes=[],
            kosgu_codes=["0.0.0"],
            purpose_codes=["ОБ-1"],
            funding_sources=["Региональные средства"],
            document_numbers=["Ф.2025.0003"],
            document_ids=[],
        )

    def test_live_text_query_resolves_metric_and_object(self) -> None:
        result = resolve_text_query_to_request_patch(
            text_query="Покажи лимиты по Благовещенску по месяцам",
            filter_options=self.filter_options,
        )

        self.assertIn("limits", result.metrics or [])
        self.assertEqual(result.filters.object_query, "Благовещенск")
        self.assertIn("month", result.group_by or [])

    def test_live_text_query_resolves_contracts(self) -> None:
        result = resolve_text_query_to_request_patch(
            text_query="Покажи сумму контрактов по источнику gz",
            filter_options=self.filter_options,
        )

        self.assertIn("contract_amount", result.metrics or [])
        self.assertIn("gz", result.filters.source_groups or [])


if __name__ == "__main__":
    unittest.main()
