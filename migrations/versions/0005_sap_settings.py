"""SAP connection settings and robot heartbeat

Revision ID: 0005_sap_settings
Revises: 0004_sap_job
Create Date: 2026-11-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_sap_settings"
down_revision = "0004_sap_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sap_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("system", sa.String(10)),
        sa.Column("client", sa.String(3)),
        sa.Column("connection", sa.String(100)),
        sa.Column("sap_user", sa.String(50)),
        sa.Column("language", sa.String(5)),
        sa.Column("max_failures", sa.Integer),
        sa.Column("evidence_keep_days", sa.Integer),
        sa.Column("verified_system", sa.String(10)),
        sa.Column("verified_client", sa.String(3)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("changed_by", sa.String(50)),
        sa.Column("changed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1", name="ck_sap_settings_single_row"),
    )
    op.add_column("robot_control", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("robot_control", sa.Column("robot_host", sa.String(100)))
    op.add_column("robot_control", sa.Column("saplogon_entries", sa.Text))
    op.add_column("robot_control", sa.Column("password_present", sa.Boolean))


def downgrade() -> None:
    for column in ("password_present", "saplogon_entries", "robot_host", "last_seen_at"):
        op.drop_column("robot_control", column)
    op.drop_table("sap_settings")
