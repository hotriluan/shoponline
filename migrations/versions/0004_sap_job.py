"""SAP job queue for the robot and the robot stop switch

Revision ID: 0004_sap_job
Revises: 0003_sap_so_ref
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_sap_job"
down_revision = "0003_sap_so_ref"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('PENDING', 'RUNNING', 'UNKNOWN', 'NEED_REVIEW')"


def upgrade() -> None:
    op.create_table(
        "sap_job",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("target_system", sa.String(10), nullable=False),
        sa.Column("target_client", sa.String(3), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("payload", sa.Text, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("evidence_path", sa.String(500)),
        sa.Column("import_batch_id", sa.Integer, sa.ForeignKey("import_batch.id")),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED', 'UNKNOWN', 'NEED_REVIEW')",
            name="ck_sap_job_status",
        ),
    )
    op.create_index("ix_sap_job_status", "sap_job", ["status"])
    # A job that is not finished blocks a second job with the same key.
    op.create_index(
        "uq_sap_job_active_key",
        "sap_job",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )
    op.create_table(
        "robot_control",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("paused_reason", sa.Text),
        sa.Column("changed_by", sa.String(50)),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("id = 1", name="ck_robot_control_single_row"),
    )
    op.execute("INSERT INTO robot_control (id, paused, consecutive_failures) VALUES (1, false, 0)")


def downgrade() -> None:
    op.drop_table("robot_control")
    op.drop_table("sap_job")
