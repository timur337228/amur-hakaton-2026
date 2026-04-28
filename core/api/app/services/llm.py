from __future__ import annotations

import json
import re
from http.client import RemoteDisconnected
from socket import timeout as SocketTimeout
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
    "metrics must be an array of strings or null. "
    "group_by must be an array of strings or null. "
    "filters.source_groups must be an array of strings or null. "
    "All other filters must be a single string or null, never arrays. "
    "If the user asks for one metric, return exactly one metric and do not add other metrics. "
    "If the user asks about a city, settlement, object, budget or municipality like Благовещенск, "
    "prefer filters.object_query instead of filters.organization_query. "
    "Use filters.organization_query only when the user explicitly asks for an organization, institution, department or ministry. "
    "If the user asks 'по месяцам', return group_by=['month']. "
    "If the user asks 'по годам', return group_by=['year']. "
    "If the user does not explicitly mention dates, return date_from and date_to as null. "
    "Do not expand an unspecified request into all available metrics. "
    "If a field is not mentioned, omit it or set it to null."
)

METRIC_HINTS = {
    "limits": ("лимит",),
    "cash_payments": ("кассов", "выбыти"),
    "agreement_amount": ("соглаш",),
    "contract_amount": ("контракт", "договор"),
    "contract_payment": ("платеж", "оплат"),
    "obligations_without_bo": ("без бо",),
    "obligations": ("обязатель", "бо"),
    "remaining_limits": ("остаток лимит",),
}

GROUP_BY_HINTS = {
    "month": ("по месяц", "помесяч", "ежемесяч"),
    "year": ("по год", "ежегод"),
    "day": ("по дням", "по датам", "по дня"),
}

LIST_FIELDS = {"metrics", "group_by", "source_groups"}
SCALAR_FILTER_FIELDS = {
    "object_query",
    "budget_query",
    "organization_query",
    "document_id",
    "document_number",
    "kfsr_code",
    "kcsr_code",
    "kvr_code",
    "kvsr_code",
    "kesr_code",
    "kosgu_code",
    "purpose_code",
    "funding_source",
}


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
    except (RemoteDisconnected, SocketTimeout, TimeoutError, OSError) as exc:
        raise LLMServiceError(f"LLM request failed: {exc}") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMServiceError("LLM response did not contain message content.") from exc

    json_text = _extract_json_text(content)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise LLMServiceError("LLM response was not valid JSON.") from exc

    normalized = _normalize_llm_payload(parsed, text_query=text_query, filter_options=filter_options)
    return AnalyticsLLMInterpretation.model_validate(normalized)


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


def _normalize_llm_payload(
    parsed: dict,
    *,
    text_query: str,
    filter_options: AnalyticsFilterOptionsResponse,
) -> dict:
    normalized_filters = _normalize_filters(parsed.get("filters"), filter_options)
    normalized = {
        "date_from": _normalize_scalar(parsed.get("date_from")),
        "date_to": _normalize_scalar(parsed.get("date_to")),
        "metrics": _normalize_allowed_list(parsed.get("metrics"), filter_options.metrics),
        "filters": normalized_filters,
        "group_by": _normalize_group_by(parsed.get("group_by")),
    }
    _apply_text_heuristics(normalized, text_query=text_query, filter_options=filter_options)
    return normalized


def _normalize_filters(raw_filters: object, filter_options: AnalyticsFilterOptionsResponse) -> dict:
    data = raw_filters if isinstance(raw_filters, dict) else {}
    filters: dict[str, object] = {
        "source_groups": _normalize_allowed_list(data.get("source_groups"), filter_options.source_groups),
    }
    for field_name in SCALAR_FILTER_FIELDS:
        filters[field_name] = _normalize_scalar(data.get(field_name))
    return filters


def _normalize_group_by(raw_value: object) -> list[str] | None:
    items = _normalize_string_list(raw_value)
    if not items:
        return None
    allowed = {"day", "month", "year", "budget_name", "object_name", "organization_name", "source_group", "metric",
        "kfsr_code", "kcsr_code", "kvr_code", "kvsr_code", "kesr_code", "kosgu_code", "purpose_code", "funding_source"}
    return [item for item in items if item in allowed] or None


def _normalize_allowed_list(raw_value: object, allowed_values: list[str]) -> list[str] | None:
    items = _normalize_string_list(raw_value)
    if not items:
        return None
    normalized_allowed = {_normalize_text(value): value for value in allowed_values}
    result: list[str] = []
    for item in items:
        canonical = normalized_allowed.get(_normalize_text(item))
        if canonical and canonical not in result:
            result.append(canonical)
    return result or None


def _normalize_string_list(raw_value: object) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [raw_value.strip()] if raw_value.strip() else []
    if isinstance(raw_value, list):
        result: list[str] = []
        for item in raw_value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    text = str(raw_value).strip()
    return [text] if text else []


def _normalize_scalar(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, list):
        for item in raw_value:
            text = _normalize_scalar(item)
            if text:
                return text
        return None
    text = str(raw_value).strip()
    return text or None


def _apply_text_heuristics(normalized: dict, *, text_query: str, filter_options: AnalyticsFilterOptionsResponse) -> None:
    lowered = _normalize_text(text_query)
    if not normalized.get("metrics"):
        inferred_metric = _infer_metric_from_text(lowered)
        if inferred_metric and inferred_metric in filter_options.metrics:
            normalized["metrics"] = [inferred_metric]

    inferred_group_by = _infer_group_by_from_text(lowered)
    if inferred_group_by:
        normalized["group_by"] = inferred_group_by
    elif normalized.get("group_by") == ["month"]:
        normalized["group_by"] = None

    filters = normalized["filters"]
    organization_query = filters.get("organization_query")
    object_query = filters.get("object_query")
    budget_query = filters.get("budget_query")
    if organization_query and not object_query and not budget_query:
        organization_matches = _matches_any_option(organization_query, filter_options.organizations)
        object_matches = _matches_any_option(organization_query, filter_options.objects) or _matches_any_option(
            organization_query, filter_options.budgets
        )
        if object_matches and not organization_matches:
            filters["object_query"] = _infer_object_query(text_query, filter_options) or organization_query
            filters["organization_query"] = None

    if not filters.get("object_query"):
        inferred_object = _infer_object_query(text_query, filter_options)
        if inferred_object and not filters.get("organization_query"):
            filters["object_query"] = inferred_object


def _infer_metric_from_text(lowered_text: str) -> str | None:
    for metric, hints in METRIC_HINTS.items():
        if any(hint in lowered_text for hint in hints):
            return metric
    return None


def _infer_group_by_from_text(lowered_text: str) -> list[str] | None:
    for group_by, hints in GROUP_BY_HINTS.items():
        if any(hint in lowered_text for hint in hints):
            return [group_by]
    return None


def _infer_object_query(text_query: str, filter_options: AnalyticsFilterOptionsResponse) -> str | None:
    terms = [term for term in re.split(r"[^A-Za-zА-Яа-я0-9Ёё-]+", text_query) if len(term) >= 4]
    for term in terms:
        if _matches_any_option(term, filter_options.objects) or _matches_any_option(term, filter_options.budgets):
            return term
    return None


def _matches_any_option(value: str, options: list[str]) -> bool:
    query = _normalize_text(value)
    return any(query and query in _normalize_text(option) for option in options)


def _normalize_text(value: str) -> str:
    return value.lower().replace("ё", "е").strip()
