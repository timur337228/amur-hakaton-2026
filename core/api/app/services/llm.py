from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..config import get_settings
from ..schemas import AnalyticsFilterOptionsResponse, AnalyticsLLMInterpretation


class LLMConfigurationError(RuntimeError):
    pass


class LLMServiceError(RuntimeError):
    pass


SYSTEM_PROMPT = (
    "You convert a user's Russian analytics request into JSON filters for a budget analytics API. "
    "Do not generate SQL. Return only valid JSON with keys: "
    "date_from, date_to, metrics, filters, group_by. "
    "filters may contain only: source_groups, object_query, budget_query, organization_query, "
    "document_id, document_number, kfsr_code, kcsr_code, kvr_code, kvsr_code, kesr_code, "
    "kosgu_code, purpose_code, funding_source. "
    "Use only metrics and source groups that exist in the provided dataset options. "
    "If the user does not explicitly mention dates, return date_from and date_to as null. "
    "Do not expand an unspecified request into all available metrics. "
    "If a field is not mentioned, omit it or set it to null."
)


def resolve_text_query_to_request_patch(
    *,
    text_query: str,
    filter_options: AnalyticsFilterOptionsResponse,
) -> AnalyticsLLMInterpretation:
    settings = get_settings()
    if not settings.llm_api_key:
        raise LLMConfigurationError("LLM API key is not configured in .env.")
    if not settings.llm_model:
        raise LLMConfigurationError("LLM model is not configured in config.yaml.")
    user_payload = {
        "task": "Convert the text into API request fields.",
        "text_query": text_query,
        "dataset_options": filter_options.model_dump(mode="json"),
    }
    body = {
        "model": settings.llm_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    request = Request(
        settings.llm_base_url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise LLMServiceError(f"LLM request failed with status {exc.code}: {details}") from exc
    except URLError as exc:
        raise LLMServiceError(f"LLM request failed: {exc.reason}") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMServiceError("LLM response did not contain message content.") from exc

    json_text = _extract_json_text(content)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LLMServiceError("LLM response was not valid JSON.") from exc

    return AnalyticsLLMInterpretation.model_validate(parsed)


def _extract_json_text(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise LLMServiceError("LLM response did not include a JSON object.")
    return cleaned[start : end + 1]
