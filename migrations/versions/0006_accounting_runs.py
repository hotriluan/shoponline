"""Ledger of deliveries sent to accounting, and the export runs

Revision ID: 0006_accounting_runs
Revises: 0005_sap_settings
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_accounting_runs"
down_revision = "0005_sap_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounting_run",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finalized_by", sa.String(50)),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("missing_note", sa.Text),
        sa.Column("generated_file_id", sa.Integer, sa.ForeignKey("generated_file.id")),
        sa.CheckConstraint(
            "status IN ('OPEN', 'FINALIZED', 'CANCELLED', 'REVOKED')",
            name="ck_accounting_run_status",
        ),
    )
    # At most one run is open at a time.
    op.create_index(
        "uq_accounting_run_open",
        "accounting_run",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )
    op.create_table(
        "accounting_run_read",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("accounting_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "platform", sa.String(20), sa.ForeignKey("platform_setting.platform"), nullable=False
        ),
        sa.Column("gi_date", sa.Date, nullable=False),
        sa.Column("sap_job_id", sa.Integer, sa.ForeignKey("sap_job.id")),
        sa.UniqueConstraint("run_id", "platform", "gi_date"),
    )
    op.create_table(
        "accounting_run_source",
        sa.Column(
            "run_id",
            sa.Integer,
            sa.ForeignKey("accounting_run.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id"), primary_key=True
        ),
        sa.Column("coverage", sa.Text, nullable=False, server_default="[]"),
    )
    op.create_table(
        "accounting_sent_delivery",
        sa.Column("delivery", sa.String(20), primary_key=True),
        sa.Column("run_id", sa.Integer, sa.ForeignKey("accounting_run.id")),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "accounting_baseline",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cutoff_date", sa.Date, nullable=False),
        sa.CheckConstraint("id = 1", name="ck_accounting_baseline_single_row"),
    )
    from shoponline.accounting.ledger import seed_baseline

    seed_baseline(op.get_bind())


def downgrade() -> None:
    op.drop_table("accounting_baseline")
    op.drop_table("accounting_sent_delivery")
    op.drop_table("accounting_run_source")
    op.drop_table("accounting_run_read")
    op.drop_table("accounting_run")
