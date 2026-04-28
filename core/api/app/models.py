from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    input_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created", index=True)
    message: Mapped[str | None] = mapped_column(Text)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    csv_files: Mapped[int] = mapped_column(Integer, default=0)
    raw_rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    normalized_rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    files: Mapped[list["RawFile"]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class RawFile(Base):
    __tablename__ = "raw_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    source_group: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered", index=True)
    encoding: Mapped[str | None] = mapped_column(String(32))
    delimiter: Mapped[str | None] = mapped_column(String(8))
    header_row_index: Mapped[int | None] = mapped_column(Integer)
    rows_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    normalized_rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    batch: Mapped[ImportBatch] = relationship(back_populates="files")


class RawRow(Base):
    __tablename__ = "raw_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class ImportErrorLog(Base):
    __tablename__ = "import_error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.id", ondelete="SET NULL"))
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="error")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BudgetFact(Base):
    __tablename__ = "budget_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number: Mapped[int | None] = mapped_column(Integer)
    source_group: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(1024), nullable=False)
    budget_name: Mapped[str | None] = mapped_column(Text)
    object_name: Mapped[str | None] = mapped_column(Text)
    organization_name: Mapped[str | None] = mapped_column(Text)
    document_number: Mapped[str | None] = mapped_column(String(256))
    document_id: Mapped[str | None] = mapped_column(String(128), index=True)
    date: Mapped[date | None] = mapped_column(Date, index=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    month: Mapped[int | None] = mapped_column(Integer, index=True)
    kfsr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kcsr_code: Mapped[str | None] = mapped_column(String(128), index=True)
    kvr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kvsr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kesr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kosgu_code: Mapped[str | None] = mapped_column(String(64), index=True)
    purpose_code: Mapped[str | None] = mapped_column(String(128), index=True)
    funding_source: Mapped[str | None] = mapped_column(Text)
    metric: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class Agreement(Base):
    __tablename__ = "agreements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    document_id: Mapped[str | None] = mapped_column(String(128), index=True)
    reg_number: Mapped[str | None] = mapped_column(String(256), index=True)
    close_date: Mapped[date | None] = mapped_column(Date)
    budget_name: Mapped[str | None] = mapped_column(Text)
    recipient_name: Mapped[str | None] = mapped_column(Text)
    amount_1year: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    kfsr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kcsr_code: Mapped[str | None] = mapped_column(String(128), index=True)
    kvr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    purpose_code: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    con_document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    con_number: Mapped[str | None] = mapped_column(String(256), index=True)
    con_date: Mapped[date | None] = mapped_column(Date)
    con_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    zakazchik_key: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class ContractBudgetLine(Base):
    __tablename__ = "contract_budget_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    con_document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    kfsr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kcsr_code: Mapped[str | None] = mapped_column(String(128), index=True)
    kvr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kesr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kvsr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    purpose_code: Mapped[str | None] = mapped_column(String(128), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    con_document_id: Mapped[str | None] = mapped_column(String(128), index=True)
    platezhka_key: Mapped[str | None] = mapped_column(String(128), index=True)
    platezhka_num: Mapped[str | None] = mapped_column(String(256))
    platezhka_paydate: Mapped[date | None] = mapped_column(Date, index=True)
    platezhka_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)


class InstitutionPayment(Base):
    __tablename__ = "institution_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_file_id: Mapped[int] = mapped_column(ForeignKey("raw_files.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer)
    budget_name: Mapped[str | None] = mapped_column(Text)
    date: Mapped[date | None] = mapped_column(Date, index=True)
    organization_name: Mapped[str | None] = mapped_column(Text)
    grantor_name: Mapped[str | None] = mapped_column(Text)
    kfsr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kcsr_code: Mapped[str | None] = mapped_column(String(128), index=True)
    kvr_code: Mapped[str | None] = mapped_column(String(64), index=True)
    kosgu_code: Mapped[str | None] = mapped_column(String(64), index=True)
    subsidy_code: Mapped[str | None] = mapped_column(String(128), index=True)
    amount_with_refund: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    amount_execution: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    amount_recovery: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)


Index("ix_budget_facts_batch_metric_year", BudgetFact.batch_id, BudgetFact.metric, BudgetFact.year)
Index("ix_budget_facts_codes", BudgetFact.kfsr_code, BudgetFact.kcsr_code, BudgetFact.kvr_code)
