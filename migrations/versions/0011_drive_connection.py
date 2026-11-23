"""Google Drive connection state (schema ops, idempotent: see 0010_backup)

Revision ID: 0011_drive_connection
Revises: 0010_backup
Create Date: 2026-11-23

The client secret and the refresh token are not here: they live in the Windows Credential
Manager. This row holds only non-secret state.
"""

from alembic import op

revision = "0011_drive_connection"
down_revision = "0010_backup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.drive_connection (
            id integer PRIMARY KEY CHECK (id = 1),
            client_id varchar(200),
            folder_id varchar(200),
            account_email varchar(200),
            status varchar(20) NOT NULL DEFAULT 'disconnected',
            last_error text,
            checked_at timestamptz,
            device_code varchar(500),
            user_code varchar(50),
            verification_url varchar(200),
            device_expires_at timestamptz,
            poll_interval integer,
            changed_by varchar(50),
            changed_at timestamptz
        )
        """
    )
    op.execute("INSERT INTO ops.drive_connection (id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.drive_connection")
