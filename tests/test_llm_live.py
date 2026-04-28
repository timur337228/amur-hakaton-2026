from __future__ import annotations

import os
import unittest
from dataclasses import dataclass

from core.api.app.schemas import AnalyticsFilterOptionsResponse, AnalyticsQueryRequest
from core.api.app.services.llm import resolve_text_query_to_request_patch


def _has_live_llm_config() -> bool:
    key_names = ("LLM_API_KEY", "OPENAI_API_KEY", "THREE_ZERO_TWO_API_KEY", "API_KEY_302AI")
    has_key = any(os.getenv(name) for name in key_names)
    return os.getenv("RUN_LIVE_LLM_TESTS", "").lower() in {"1", "true", "yes", "on"} and has_key


@dataclass(frozen=True)
class LLMQueryCase:
    text_query: str
    expected_request: dict


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
        self.cases = [
            LLMQueryCase(
                text_query="Покажи лимиты по Благовещенску по месяцам",
                expected_request={
                    "metrics": ["limits"],
                    "filters": {"object_query": "Благовещенск"},
                    "group_by": ["month"],
                },
            ),
            LLMQueryCase(
                text_query="Покажи сумму контрактов по источнику gz",
                expected_request={
                    "metrics": ["contract_amount"],
                    "filters": {"source_groups": ["gz"]},
                },
            ),
            LLMQueryCase(
                text_query="Покажи кассовые выплаты по 0502",
                expected_request={
                    "metrics": ["cash_payments"],
                    "filters": {"kfsr_code": "0502"},
                },
            ),
        ]

    def test_live_text_queries_map_to_api_requests(self) -> None:
        for case in self.cases:
            with self.subTest(text_query=case.text_query):
                result = resolve_text_query_to_request_patch(
                    text_query=case.text_query,
                    filter_options=self.filter_options,
                )
                actual_request = _normalize_request_patch(result, text_query=case.text_query)
                self.assertEqual(actual_request, case.expected_request)


def _normalize_request_patch(result, *, text_query: str) -> dict:
    request = AnalyticsQueryRequest(batch_id="live-test-batch")
    normalized = request.model_copy(
        update={
            "metrics": result.metrics,
            "date_from": result.date_from,
            "date_to": result.date_to,
            "group_by": result.group_by or ["month"],
            "filters": result.filters,
        }
    )
    payload = normalized.model_dump(mode="json", exclude_none=True)
    payload.pop("batch_id", None)
    payload.pop("text_query", None)
    payload.pop("limit", None)
    payload.pop("offset", None)
    payload.pop("include_rows", None)
    payload.pop("include_charts", None)
    lowered = text_query.lower().replace("ё", "е")
    mentions_grouping = any(token in lowered for token in ("по месяц", "помесяч", "по год", "ежегод", "по дня", "по дат"))
    if payload.get("group_by") == ["month"] and not mentions_grouping:
        payload.pop("group_by", None)
    return payload


if __name__ == "__main__":
    unittest.main()
