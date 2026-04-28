from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .csv_reader import find_header_row, read_csv, row_to_dict
from .normalization import (
    clean_text,
    date_parts,
    detect_date_from_filename,
    normalize_code,
    normalize_header,
    parse_amount,
    parse_date,
)


@dataclass
class ParsedCsvFile:
    encoding: str
    delimiter: str
    header_row_index: int
    rows_count: int
    raw_rows: list[dict] = field(default_factory=list)
    budget_facts: list[dict] = field(default_factory=list)
    agreements: list[dict] = field(default_factory=list)
    contracts: list[dict] = field(default_factory=list)
    contract_budget_lines: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    institution_payments: list[dict] = field(default_factory=list)


def parse_csv_file(path: Path, relative_path: str, source_group: str) -> ParsedCsvFile:
    csv_data = read_csv(path)
    header_row_index = find_header_row(csv_data.rows, source_group)
    headers = csv_data.rows[header_row_index] if csv_data.rows else []
    data_rows = csv_data.rows[header_row_index + 1 :] if csv_data.rows else []

    parsed = ParsedCsvFile(
        encoding=csv_data.encoding,
        delimiter=csv_data.delimiter,
        header_row_index=header_row_index,
        rows_count=len(data_rows),
    )

    for offset, row in enumerate(data_rows, start=header_row_index + 2):
        if not any(cell.strip() for cell in row):
            continue

        raw = row_to_dict(headers, row)
        if _looks_like_total_row(raw):
            continue

        parsed.raw_rows.append({"row_number": offset, "data": raw})

        if source_group == "rchb":
            parsed.budget_facts.extend(_parse_rchb_row(raw, offset, relative_path))
        elif source_group == "agreements":
            agreement, fact = _parse_agreement_row(raw, offset, relative_path, path)
            if agreement:
                parsed.agreements.append(agreement)
            if fact:
                parsed.budget_facts.append(fact)
        elif source_group == "gz":
            _parse_gz_row(raw, offset, relative_path, parsed)
        elif source_group == "buau":
            payment, facts = _parse_buau_row(raw, offset, relative_path)
            if payment:
                parsed.institution_payments.append(payment)
            parsed.budget_facts.extend(facts)

    return parsed


def _parse_rchb_row(raw: dict[str, str], row_number: int, source_file: str) -> list[dict]:
    operation_date = _get_date(raw, "Дата проводки")
    year, month = date_parts(operation_date)
    budget_name = _get(raw, "Бюджет")
    organization = _get(raw, "Наименование КВСР")
    purpose_code = _get(raw, "Код цели")

    base = {
        "row_number": row_number,
        "source_group": "rchb",
        "source_file": source_file,
        "budget_name": budget_name,
        "object_name": budget_name,
        "organization_name": organization,
        "date": operation_date,
        "year": year,
        "month": month,
        "kfsr_code": normalize_code(_get(raw, "КФСР")),
        "kcsr_code": normalize_code(_get(raw, "КЦСР")),
        "kvr_code": normalize_code(_get(raw, "КВР")),
        "kvsr_code": normalize_code(_get(raw, "КВСР")),
        "kesr_code": normalize_code(_get(raw, "КОСГУ")),
        "kosgu_code": normalize_code(_get(raw, "КОСГУ")),
        "purpose_code": normalize_code(purpose_code),
        "funding_source": _get(raw, "Источник средств"),
        "raw_data": raw,
    }

    metrics = {
        "limits": _find_amount(raw, "лимитыпбс"),
        "obligations": _find_amount(raw, "подтвлимитовпобо"),
        "obligations_without_bo": _find_amount(raw, "подтвлимитовбезбо"),
        "remaining_limits": _find_amount(raw, "остатоклимитов"),
        "cash_payments": _find_amount(raw, "всеговыбытий"),
    }

    facts = []
    for metric, value in metrics.items():
        if value is None or value == Decimal("0.00"):
            continue
        facts.append({**base, "metric": metric, "value": value})
    return facts


def _parse_agreement_row(
    raw: dict[str, str], row_number: int, source_file: str, path: Path
) -> tuple[dict | None, dict | None]:
    amount = parse_amount(_get(raw, "amount_1year"))
    close_date = _get_date(raw, "close_date") or detect_date_from_filename(path)
    year, month = date_parts(close_date)
    document_id = _get(raw, "document_id")
    reg_number = _get(raw, "reg_number")
    budget_name = _get(raw, "caption")
    recipient_name = _get(raw, "dd_recipient_caption")
    purpose_code = normalize_code(_get(raw, "dd_purposefulgrant_code"))

    agreement = {
        "row_number": row_number,
        "document_id": document_id,
        "reg_number": reg_number,
        "close_date": close_date,
        "budget_name": budget_name,
        "recipient_name": recipient_name,
        "amount_1year": amount,
        "kfsr_code": normalize_code(_get(raw, "kfsr_code")),
        "kcsr_code": normalize_code(_get(raw, "kcsr_code")),
        "kvr_code": normalize_code(_get(raw, "kvr_code")),
        "purpose_code": purpose_code,
        "raw_data": raw,
    }

    fact = None
    if amount is not None and amount != Decimal("0.00"):
        fact = {
            "row_number": row_number,
            "source_group": "agreements",
            "source_file": source_file,
            "budget_name": budget_name,
            "object_name": recipient_name or budget_name,
            "organization_name": recipient_name,
            "document_number": reg_number,
            "document_id": document_id,
            "date": close_date,
            "year": year,
            "month": month,
            "kfsr_code": agreement["kfsr_code"],
            "kcsr_code": agreement["kcsr_code"],
            "kvr_code": agreement["kvr_code"],
            "purpose_code": purpose_code,
            "metric": "agreement_amount",
            "value": amount,
            "raw_data": raw,
        }
    return agreement, fact


def _parse_gz_row(raw: dict[str, str], row_number: int, source_file: str, parsed: ParsedCsvFile) -> None:
    normalized_file = source_file.lower().replace("ё", "е")
    con_document_id = _get(raw, "con_document_id")

    if "контракт" in normalized_file or "договор" in normalized_file:
        amount = parse_amount(_get(raw, "con_amount"))
        con_date = _get_date(raw, "con_date")
        year, month = date_parts(con_date)
        contract = {
            "row_number": row_number,
            "con_document_id": con_document_id,
            "con_number": _get(raw, "con_number"),
            "con_date": con_date,
            "con_amount": amount,
            "zakazchik_key": _get(raw, "zakazchik_key"),
            "raw_data": raw,
        }
        parsed.contracts.append(contract)
        if amount is not None and amount != Decimal("0.00"):
            parsed.budget_facts.append(
                {
                    "row_number": row_number,
                    "source_group": "gz",
                    "source_file": source_file,
                    "object_name": contract["zakazchik_key"],
                    "organization_name": contract["zakazchik_key"],
                    "document_number": contract["con_number"],
                    "document_id": con_document_id,
                    "date": con_date,
                    "year": year,
                    "month": month,
                    "metric": "contract_amount",
                    "value": amount,
                    "raw_data": raw,
                }
            )
        return

    if "бюджетные" in normalized_file:
        parsed.contract_budget_lines.append(
            {
                "row_number": row_number,
                "con_document_id": con_document_id,
                "kfsr_code": normalize_code(_get(raw, "kfsr_code")),
                "kcsr_code": normalize_code(_get(raw, "kcsr_code")),
                "kvr_code": normalize_code(_get(raw, "kvr_code")),
                "kesr_code": normalize_code(_get(raw, "kesr_code")),
                "kvsr_code": normalize_code(_get(raw, "kvsr_code")),
                "purpose_code": normalize_code(_get(raw, "purposefulgrant")),
                "raw_data": raw,
            }
        )
        return

    if "платеж" in normalized_file:
        amount = parse_amount(_get(raw, "platezhka_amount"))
        pay_date = _get_date(raw, "platezhka_paydate")
        year, month = date_parts(pay_date)
        payment = {
            "row_number": row_number,
            "con_document_id": con_document_id,
            "platezhka_key": _get(raw, "platezhka_key"),
            "platezhka_num": _get(raw, "platezhka_num"),
            "platezhka_paydate": pay_date,
            "platezhka_amount": amount,
            "raw_data": raw,
        }
        parsed.payments.append(payment)
        if amount is not None and amount != Decimal("0.00"):
            parsed.budget_facts.append(
                {
                    "row_number": row_number,
                    "source_group": "gz",
                    "source_file": source_file,
                    "document_number": payment["platezhka_num"],
                    "document_id": con_document_id,
                    "date": pay_date,
                    "year": year,
                    "month": month,
                    "metric": "contract_payment",
                    "value": amount,
                    "raw_data": raw,
                }
            )


def _parse_buau_row(raw: dict[str, str], row_number: int, source_file: str) -> tuple[dict | None, list[dict]]:
    operation_date = _get_date(raw, "Дата проводки")
    year, month = date_parts(operation_date)
    budget_name = _get(raw, "Бюджет")
    organization = _get(raw, "Организация")
    grantor = _get(raw, "Орган, предоставляющий субсидии")
    amount_with_refund = _find_amount(raw, "выплатысучетомвозврата")
    amount_execution = _find_amount(raw, "выплатыисполнение")
    amount_recovery = _find_amount(raw, "выплатывосстановление")

    payment = {
        "row_number": row_number,
        "budget_name": budget_name,
        "date": operation_date,
        "organization_name": organization,
        "grantor_name": grantor,
        "kfsr_code": normalize_code(_get(raw, "КФСР")),
        "kcsr_code": normalize_code(_get(raw, "КЦСР")),
        "kvr_code": normalize_code(_get(raw, "КВР")),
        "kosgu_code": normalize_code(_get(raw, "КОСГУ")),
        "subsidy_code": normalize_code(_get(raw, "Код субсидии")),
        "amount_with_refund": amount_with_refund,
        "amount_execution": amount_execution,
        "amount_recovery": amount_recovery,
        "raw_data": raw,
    }

    base = {
        "row_number": row_number,
        "source_group": "buau",
        "source_file": source_file,
        "budget_name": budget_name,
        "object_name": budget_name,
        "organization_name": organization,
        "date": operation_date,
        "year": year,
        "month": month,
        "kfsr_code": payment["kfsr_code"],
        "kcsr_code": payment["kcsr_code"],
        "kvr_code": payment["kvr_code"],
        "kosgu_code": payment["kosgu_code"],
        "purpose_code": payment["subsidy_code"],
        "metric": "",
        "value": Decimal("0.00"),
        "raw_data": raw,
    }

    facts = []
    for metric, value in {
        "institution_payments_with_refund": amount_with_refund,
        "institution_payments_execution": amount_execution,
        "institution_payments_recovery": amount_recovery,
    }.items():
        if value is None or value == Decimal("0.00"):
            continue
        facts.append({**base, "metric": metric, "value": value})
    return payment, facts


def _get(raw: dict[str, str], *names: str) -> str | None:
    by_normalized = {normalize_header(key): value for key, value in raw.items()}
    for name in names:
        value = by_normalized.get(normalize_header(name))
        if value is not None:
            return clean_text(value)
    return None


def _get_date(raw: dict[str, str], name: str):
    return parse_date(_get(raw, name))


def _find_amount(raw: dict[str, str], normalized_header_contains: str) -> Decimal | None:
    needle = normalize_header(normalized_header_contains)
    for key, value in raw.items():
        if needle in normalize_header(key):
            return parse_amount(value)
    return None


def _looks_like_total_row(raw: dict[str, str]) -> bool:
    values = [clean_text(value) for value in raw.values()]
    first = next((value for value in values if value), "")
    return bool(first and first.lower() in {"итого", "всего"})
