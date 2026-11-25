"""Customer address source: which hand wrote the address now stored

Revision ID: 0017_customer_address_source
Revises: 0016_report_views
Create Date: 2026-11-25

`address_source` says whether the address came from the order file ('file'), a shipping label PDF
('label') or an admin ('admin'). NULL means the source is unknown (every row that existed before
this column): a label that disagrees with such an address asks the admin before overwriting it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_customer_address_source"
down_revision = "0016_report_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer_info", sa.Column("address_source", sa.String(10), nullable=True))
    op.create_check_constraint(
        "ck_customer_info_address_source",
        "customer_info",
        "address_source IN ('file','label','admin')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_customer_info_address_source", "customer_info", type_="check")
    op.drop_column("customer_info", "address_source")
