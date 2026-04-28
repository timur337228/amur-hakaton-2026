from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Agreement,
    BudgetFact,
    Contract,
    ContractBudgetLine,
    ImportBatch,
    ImportErrorLog,
    InstitutionPayment,
    Payment,
    RawFile,
    RawRow,
)
from .archive import extract_archive
from .parsers import parse_csv_file


DATA_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf"}


class ImportService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._seen_agreement_keys: set[tuple] = set()
        self._seen_agreement_fact_keys: set[tuple] = set()

    def create_batch(self, input_type: str, original_name: str | None) -> ImportBatch:
        batch = ImportBatch(
            id=str(uuid4()),
            input_type=input_type,
            original_name=original_name,
            status="created",
        )
        self.db.add(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def batch_root(self, batch_id: str) -> Path:
        return self.settings.storage_dir / "imports" / batch_id

    def upload_dir(self, batch_id: str) -> Path:
        return self.batch_root(batch_id) / "upload"

    def extracted_dir(self, batch_id: str) -> Path:
        return self.batch_root(batch_id) / "extracted"

    def import_archive(self, batch: ImportBatch, archive_path: Path) -> ImportBatch:
        extracted_dir = self.extracted_dir(batch.id)
        try:
            batch.status = "extracting"
            batch.started_at = _now()
            self.db.commit()
            extract_archive(archive_path, extracted_dir)
            return self.process_directory(batch, extracted_dir)
        except Exception as exc:
            self._fail_batch(batch, str(exc))
            raise

    def import_local_path(self, source_path: Path, original_name: str | None = None) -> ImportBatch:
        batch = self.create_batch("local_path", original_name or str(source_path))
        extracted_dir = self.extracted_dir(batch.id)

        try:
            batch.status = "copying"
            batch.started_at = _now()
            self.db.commit()
            _copy_path(source_path, extracted_dir)
            return self.process_directory(batch, extracted_dir)
        except Exception as exc:
            self._fail_batch(batch, str(exc))
            raise

    def process_directory(self, batch: ImportBatch, root: Path) -> ImportBatch:
        batch.status = "processing"
        batch.started_at = batch.started_at or _now()
        self.db.commit()

        files = [path for path in root.rglob("*") if path.is_file()]
        batch.total_files = len(files)
        batch.csv_files = sum(1 for path in files if path.suffix.lower() == ".csv")
        self.db.commit()

        for path in files:
            if path.suffix.lower() not in DATA_EXTENSIONS:
                continue
            self._register_and_process_file(batch, root, path)

        batch.status = "completed" if batch.error_count == 0 else "completed_with_errors"
        batch.finished_at = _now()
        batch.message = (
            f"Imported {batch.raw_rows_imported} raw rows and "
            f"{batch.normalized_rows_imported} normalized rows from {batch.csv_files} CSV files."
        )
        self.db.commit()
        self.db.refresh(batch)
        return batch

    def _register_and_process_file(self, batch: ImportBatch, root: Path, path: Path) -> None:
        relative_path = path.relative_to(root).as_posix()
        raw_file = RawFile(
            batch_id=batch.id,
            relative_path=relative_path,
            original_name=path.name,
            extension=path.suffix.lower(),
            source_group=detect_source_group(relative_path),
            size_bytes=path.stat().st_size,
            sha256=_sha256(path),
            status="registered",
        )
        self.db.add(raw_file)
        self.db.flush()
        self.db.commit()
        self.db.refresh(raw_file)

        if raw_file.extension != ".csv":
            raw_file.status = "skipped"
            raw_file.error_message = "Only CSV files are parsed at this stage; file was registered only."
            self.db.commit()
            return

        try:
            parsed = parse_csv_file(path, relative_path, raw_file.source_group)
            self._deduplicate_parsed_rows(raw_file.source_group, parsed)
            raw_file.status = "processed"
            raw_file.encoding = parsed.encoding
            raw_file.delimiter = parsed.delimiter
            raw_file.header_row_index = parsed.header_row_index
            raw_file.rows_count = parsed.rows_count
            raw_file.raw_rows_imported = len(parsed.raw_rows)
            raw_file.normalized_rows_imported = (
                len(parsed.budget_facts)
                + len(parsed.agreements)
                + len(parsed.contracts)
                + len(parsed.contract_budget_lines)
                + len(parsed.payments)
                + len(parsed.institution_payments)
            )

            self._bulk_insert(raw_file, parsed)
            batch.raw_rows_imported += raw_file.raw_rows_imported
            batch.normalized_rows_imported += raw_file.normalized_rows_imported
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raw_file.status = "error"
            raw_file.error_message = str(exc)
            batch.error_count += 1
            self.db.add(raw_file)
            self.db.add(
                ImportErrorLog(
                    batch_id=batch.id,
                    raw_file_id=raw_file.id,
                    level="error",
                    message=str(exc),
                    context={"relative_path": relative_path},
                )
            )
            self.db.commit()

    def _bulk_insert(self, raw_file: RawFile, parsed) -> None:
        common = {"batch_id": raw_file.batch_id, "raw_file_id": raw_file.id}

        if parsed.raw_rows:
            self.db.bulk_insert_mappings(
                RawRow,
                [{**common, **row} for row in parsed.raw_rows],
            )

        _insert_mappings(self.db, BudgetFact, parsed.budget_facts, common)
        _insert_mappings(self.db, Agreement, parsed.agreements, common)
        _insert_mappings(self.db, Contract, parsed.contracts, common)
        _insert_mappings(self.db, ContractBudgetLine, parsed.contract_budget_lines, common)
        _insert_mappings(self.db, Payment, parsed.payments, common)
        _insert_mappings(self.db, InstitutionPayment, parsed.institution_payments, common)

    def _deduplicate_parsed_rows(self, source_group: str, parsed) -> None:
        if source_group != "agreements":
            return

        unique_agreements: list[dict] = []
        for row in parsed.agreements:
            key = _agreement_key(row)
            if key in self._seen_agreement_keys:
                continue
            self._seen_agreement_keys.add(key)
            unique_agreements.append(row)
        parsed.agreements = unique_agreements

        unique_facts: list[dict] = []
        for row in parsed.budget_facts:
            if row.get("source_group") != "agreements" or row.get("metric") != "agreement_amount":
                unique_facts.append(row)
                continue
            key = _agreement_fact_key(row)
            if key in self._seen_agreement_fact_keys:
                continue
            self._seen_agreement_fact_keys.add(key)
            unique_facts.append(row)
        parsed.budget_facts = unique_facts

    def _fail_batch(self, batch: ImportBatch, message: str) -> None:
        batch.status = "failed"
        batch.message = message
        batch.error_count += 1
        batch.finished_at = _now()
        self.db.add(ImportErrorLog(batch_id=batch.id, level="error", message=message))
        self.db.commit()


def detect_source_group(relative_path: str) -> str:
    lowered = relative_path.lower().replace("ё", "е").replace("\\", "/")
    if "рчб" in lowered or "/1." in lowered or lowered.startswith("1."):
        return "rchb"
    if "соглаш" in lowered or "/2." in lowered or lowered.startswith("2."):
        return "agreements"
    if "гз" in lowered or "/3." in lowered or lowered.startswith("3."):
        return "gz"
    if "буау" in lowered or "/4." in lowered or lowered.startswith("4."):
        return "buau"
    if "скк" in lowered:
        return "control_example"
    return "unknown"


def _insert_mappings(db: Session, model, rows: list[dict], common: dict) -> None:
    if not rows:
        return
    db.bulk_insert_mappings(model, [{**common, **row} for row in rows])


def _copy_path(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        for child in source.rglob("*"):
            if child.is_dir():
                continue
            target = destination / child.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
        return

    if source.is_file():
        shutil.copy2(source, destination / source.name)
        return

    raise FileNotFoundError(f"Source path does not exist: {source}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _agreement_key(row: dict) -> tuple:
    return (
        row.get("document_id") or "",
        row.get("reg_number") or "",
        row.get("close_date"),
        row.get("amount_1year"),
        row.get("recipient_name") or "",
        row.get("budget_name") or "",
    )


def _agreement_fact_key(row: dict) -> tuple:
    return (
        row.get("document_id") or "",
        row.get("document_number") or "",
        row.get("date"),
        row.get("value"),
        row.get("object_name") or "",
        row.get("budget_name") or "",
        row.get("metric") or "",
    )
