from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("input_type", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("csv_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("normalized_rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_batches_status", "import_batches", ["status"], unique=False)

    op.create_table(
        "raw_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("original_name", sa.String(length=512), nullable=False),
        sa.Column("extension", sa.String(length=16), nullable=False),
        sa.Column("source_group", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="registered"),
        sa.Column("encoding", sa.String(length=32), nullable=True),
        sa.Column("delimiter", sa.String(length=8), nullable=True),
        sa.Column("header_row_index", sa.Integer(), nullable=True),
        sa.Column("rows_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("normalized_rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_files_batch_id", "raw_files", ["batch_id"], unique=False)
    op.create_index("ix_raw_files_source_group", "raw_files", ["source_group"], unique=False)
    op.create_index("ix_raw_files_status", "raw_files", ["status"], unique=False)

    op.create_table(
        "raw_rows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_rows_batch_id", "raw_rows", ["batch_id"], unique=False)
    op.create_index("ix_raw_rows_raw_file_id", "raw_rows", ["raw_file_id"], unique=False)

    op.create_table(
        "import_error_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="error"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_error_logs_batch_id", "import_error_logs", ["batch_id"], unique=False)

    op.create_table(
        "budget_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("source_group", sa.String(length=64), nullable=False),
        sa.Column("source_file", sa.String(length=1024), nullable=False),
        sa.Column("budget_name", sa.Text(), nullable=True),
        sa.Column("object_name", sa.Text(), nullable=True),
        sa.Column("organization_name", sa.Text(), nullable=True),
        sa.Column("document_number", sa.String(length=256), nullable=True),
        sa.Column("document_id", sa.String(length=128), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("kfsr_code", sa.String(length=64), nullable=True),
        sa.Column("kcsr_code", sa.String(length=128), nullable=True),
        sa.Column("kvr_code", sa.String(length=64), nullable=True),
        sa.Column("kvsr_code", sa.String(length=64), nullable=True),
        sa.Column("kesr_code", sa.String(length=64), nullable=True),
        sa.Column("kosgu_code", sa.String(length=64), nullable=True),
        sa.Column("purpose_code", sa.String(length=128), nullable=True),
        sa.Column("funding_source", sa.Text(), nullable=True),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Numeric(20, 2), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in [
        ("ix_budget_facts_batch_id", ["batch_id"]),
        ("ix_budget_facts_raw_file_id", ["raw_file_id"]),
        ("ix_budget_facts_source_group", ["source_group"]),
        ("ix_budget_facts_document_id", ["document_id"]),
        ("ix_budget_facts_date", ["date"]),
        ("ix_budget_facts_year", ["year"]),
        ("ix_budget_facts_month", ["month"]),
        ("ix_budget_facts_kfsr_code", ["kfsr_code"]),
        ("ix_budget_facts_kcsr_code", ["kcsr_code"]),
        ("ix_budget_facts_kvr_code", ["kvr_code"]),
        ("ix_budget_facts_kvsr_code", ["kvsr_code"]),
        ("ix_budget_facts_kesr_code", ["kesr_code"]),
        ("ix_budget_facts_kosgu_code", ["kosgu_code"]),
        ("ix_budget_facts_purpose_code", ["purpose_code"]),
        ("ix_budget_facts_metric", ["metric"]),
        ("ix_budget_facts_batch_metric_year", ["batch_id", "metric", "year"]),
        ("ix_budget_facts_codes", ["kfsr_code", "kcsr_code", "kvr_code"]),
    ]:
        op.create_index(name, "budget_facts", columns, unique=False)

    op.create_table(
        "agreements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.String(length=128), nullable=True),
        sa.Column("reg_number", sa.String(length=256), nullable=True),
        sa.Column("close_date", sa.Date(), nullable=True),
        sa.Column("budget_name", sa.Text(), nullable=True),
        sa.Column("recipient_name", sa.Text(), nullable=True),
        sa.Column("amount_1year", sa.Numeric(20, 2), nullable=True),
        sa.Column("kfsr_code", sa.String(length=64), nullable=True),
        sa.Column("kcsr_code", sa.String(length=128), nullable=True),
        sa.Column("kvr_code", sa.String(length=64), nullable=True),
        sa.Column("purpose_code", sa.String(length=128), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in [
        ("ix_agreements_batch_id", ["batch_id"]),
        ("ix_agreements_document_id", ["document_id"]),
        ("ix_agreements_reg_number", ["reg_number"]),
        ("ix_agreements_kfsr_code", ["kfsr_code"]),
        ("ix_agreements_kcsr_code", ["kcsr_code"]),
        ("ix_agreements_kvr_code", ["kvr_code"]),
        ("ix_agreements_purpose_code", ["purpose_code"]),
    ]:
        op.create_index(name, "agreements", columns, unique=False)

    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("con_document_id", sa.String(length=128), nullable=False),
        sa.Column("con_number", sa.String(length=256), nullable=True),
        sa.Column("con_date", sa.Date(), nullable=True),
        sa.Column("con_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("zakazchik_key", sa.String(length=128), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in [
        ("ix_contracts_batch_id", ["batch_id"]),
        ("ix_contracts_con_document_id", ["con_document_id"]),
        ("ix_contracts_con_number", ["con_number"]),
        ("ix_contracts_zakazchik_key", ["zakazchik_key"]),
    ]:
        op.create_index(name, "contracts", columns, unique=False)

    op.create_table(
        "contract_budget_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("con_document_id", sa.String(length=128), nullable=False),
        sa.Column("kfsr_code", sa.String(length=64), nullable=True),
        sa.Column("kcsr_code", sa.String(length=128), nullable=True),
        sa.Column("kvr_code", sa.String(length=64), nullable=True),
        sa.Column("kesr_code", sa.String(length=64), nullable=True),
        sa.Column("kvsr_code", sa.String(length=64), nullable=True),
        sa.Column("purpose_code", sa.String(length=128), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in [
        ("ix_contract_budget_lines_batch_id", ["batch_id"]),
        ("ix_contract_budget_lines_con_document_id", ["con_document_id"]),
        ("ix_contract_budget_lines_kfsr_code", ["kfsr_code"]),
        ("ix_contract_budget_lines_kcsr_code", ["kcsr_code"]),
        ("ix_contract_budget_lines_kvr_code", ["kvr_code"]),
        ("ix_contract_budget_lines_kesr_code", ["kesr_code"]),
        ("ix_contract_budget_lines_kvsr_code", ["kvsr_code"]),
        ("ix_contract_budget_lines_purpose_code", ["purpose_code"]),
    ]:
        op.create_index(name, "contract_budget_lines", columns, unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("con_document_id", sa.String(length=128), nullable=True),
        sa.Column("platezhka_key", sa.String(length=128), nullable=True),
        sa.Column("platezhka_num", sa.String(length=256), nullable=True),
        sa.Column("platezhka_paydate", sa.Date(), nullable=True),
        sa.Column("platezhka_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in [
        ("ix_payments_batch_id", ["batch_id"]),
        ("ix_payments_con_document_id", ["con_document_id"]),
        ("ix_payments_platezhka_key", ["platezhka_key"]),
        ("ix_payments_platezhka_paydate", ["platezhka_paydate"]),
    ]:
        op.create_index(name, "payments", columns, unique=False)

    op.create_table(
        "institution_payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("raw_file_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("budget_name", sa.Text(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("organization_name", sa.Text(), nullable=True),
        sa.Column("grantor_name", sa.Text(), nullable=True),
        sa.Column("kfsr_code", sa.String(length=64), nullable=True),
        sa.Column("kcsr_code", sa.String(length=128), nullable=True),
        sa.Column("kvr_code", sa.String(length=64), nullable=True),
        sa.Column("kosgu_code", sa.String(length=64), nullable=True),
        sa.Column("subsidy_code", sa.String(length=128), nullable=True),
        sa.Column("amount_with_refund", sa.Numeric(20, 2), nullable=True),
        sa.Column("amount_execution", sa.Numeric(20, 2), nullable=True),
        sa.Column("amount_recovery", sa.Numeric(20, 2), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_file_id"], ["raw_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in [
        ("ix_institution_payments_batch_id", ["batch_id"]),
        ("ix_institution_payments_date", ["date"]),
        ("ix_institution_payments_kfsr_code", ["kfsr_code"]),
        ("ix_institution_payments_kcsr_code", ["kcsr_code"]),
        ("ix_institution_payments_kvr_code", ["kvr_code"]),
        ("ix_institution_payments_kosgu_code", ["kosgu_code"]),
        ("ix_institution_payments_subsidy_code", ["subsidy_code"]),
    ]:
        op.create_index(name, "institution_payments", columns, unique=False)


def downgrade() -> None:
    for table_name in [
        "institution_payments",
        "payments",
        "contract_budget_lines",
        "contracts",
        "agreements",
        "budget_facts",
        "import_error_logs",
        "raw_rows",
        "raw_files",
        "import_batches",
    ]:
        op.drop_table(table_name)
