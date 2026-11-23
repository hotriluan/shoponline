"""Schema ops: web accounts and the backup records that survive a restore of the business data

Revision ID: 0010_backup
Revises: 0009_platform_settlement
Create Date: 2026-11-23

Every migration that touches schema ops must be idempotent (CREATE ... IF NOT EXISTS, check a
column before adding it). A restore on the same machine replaces only schema public, so
public.alembic_version can go back to an older revision while ops stays at the newest one; the
migrate that follows the restore then runs this file again on a database where ops is complete.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_backup"
down_revision = "0009_platform_settlement"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    found = op.get_bind().execute(sa.text("SELECT to_regclass(:n)"), {"n": name}).scalar()
    return found is not None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")

    # A restored dump brings back public.app_user next to the live ops.app_user: the live
    # accounts win (they are never rolled back by a restore).
    if _exists("ops.app_user"):
        op.execute("DROP TABLE IF EXISTS public.app_user")
    elif _exists("public.app_user"):
        op.execute("ALTER TABLE public.app_user SET SCHEMA ops")
    op.execute("ALTER TABLE ops.app_user ADD COLUMN IF NOT EXISTS last_seen_at timestamptz")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.system_state (
            id integer PRIMARY KEY CHECK (id = 1),
            session_epoch integer NOT NULL DEFAULT 0
        )
        """
    )
    op.execute("INSERT INTO ops.system_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.backup_settings (
            id integer PRIMARY KEY CHECK (id = 1),
            db_time time NOT NULL DEFAULT '16:30',
            full_weekday integer NOT NULL DEFAULT 4 CHECK (full_weekday BETWEEN 0 AND 6),
            full_time time NOT NULL DEFAULT '16:30',
            keep_db integer NOT NULL DEFAULT 15 CHECK (keep_db BETWEEN 1 AND 100),
            keep_app integer NOT NULL DEFAULT 15 CHECK (keep_app BETWEEN 1 AND 100),
            full_max_days integer NOT NULL DEFAULT 30 CHECK (full_max_days BETWEEN 7 AND 90),
            drive_on_schedule boolean NOT NULL DEFAULT true,
            changed_by varchar(50),
            changed_at timestamptz
        )
        """
    )
    op.execute("INSERT INTO ops.backup_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.backup_run (
            id serial PRIMARY KEY,
            kind varchar(10) NOT NULL CHECK (kind IN ('db', 'app', 'full')),
            source varchar(20) NOT NULL,
            actor varchar(50) NOT NULL,
            file_name varchar(200) NOT NULL,
            size_bytes bigint,
            sha256 varchar(64),
            manifest jsonb,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz,
            local_status varchar(20) NOT NULL DEFAULT 'running',
            local_error text,
            drive_requested boolean NOT NULL DEFAULT false,
            drive_status varchar(20),
            drive_file_id varchar(200),
            drive_error text,
            verified_at timestamptz,
            verify_result text,
            deleted_by varchar(50),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_backup_run_drive_file "
        "ON ops.backup_run (drive_file_id) WHERE drive_file_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_backup_run_kind_started "
        "ON ops.backup_run (kind, started_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ops.backup_request (
            id serial PRIMARY KEY,
            action varchar(20) NOT NULL,
            kind varchar(10),
            target_run_id integer REFERENCES ops.backup_run (id),
            to_drive boolean NOT NULL DEFAULT false,
            requested_by varchar(50) NOT NULL,
            requested_at timestamptz NOT NULL DEFAULT now(),
            status varchar(20) NOT NULL DEFAULT 'pending',
            started_at timestamptz,
            finished_at timestamptz,
            message text,
            result jsonb,
            safety_run_id integer REFERENCES ops.backup_run (id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_backup_request_status ON ops.backup_request (status)")


def downgrade() -> None:
    for table in ("backup_request", "backup_run", "backup_settings", "system_state"):
        op.execute(f"DROP TABLE IF EXISTS ops.{table}")
    op.execute("ALTER TABLE ops.app_user DROP COLUMN IF EXISTS last_seen_at")
    op.execute("ALTER TABLE ops.app_user SET SCHEMA public")
    op.execute("DROP SCHEMA IF EXISTS ops")
