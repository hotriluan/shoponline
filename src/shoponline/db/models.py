"""SQLAlchemy models. Schema changes go through Alembic migrations in migrations/versions."""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PlatformSetting(Base):
    __tablename__ = "platform_setting"

    platform: Mapped[str] = mapped_column(String(20), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(50))
    sap_customer: Mapped[str] = mapped_column(String(20), unique=True)
    mode: Mapped[str] = mapped_column(String(10), default="manual")


class Shop(Base):
    """A shop of a platform. `division` is written as is into the Shop Online history file."""

    __tablename__ = "shop"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    platform: Mapped[str] = mapped_column(ForeignKey("platform_setting.platform"))
    division: Mapped[str] = mapped_column(String(50), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class AppUser(Base):
    """Web accounts live in schema ops: a restore of the business data never rolls them back."""

    __tablename__ = "app_user"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base):
    """One uploaded file (platform orders, mapping table, or SAP report)."""

    __tablename__ = "import_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    platform: Mapped[str | None] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64))
    stored_path: Mapped[str] = mapped_column(String(500))
    imported_by: Mapped[str] = mapped_column(String(50))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0)
    shop_code: Mapped[str | None] = mapped_column(ForeignKey("shop.code"))


class GeneratedFile(Base):
    """A workbook produced by the system (order file, accounting file)."""

    __tablename__ = "generated_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    file_name: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderBatch(Base):
    """One platform and one processing day D."""

    __tablename__ = "order_batch"
    __table_args__ = (UniqueConstraint("platform", "processing_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(ForeignKey("platform_setting.platform"))
    processing_date: Mapped[date] = mapped_column(Date)
    gi_date: Mapped[date] = mapped_column(Date)
    confirmed_by: Mapped[str | None] = mapped_column(String(50))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    orders: Mapped[list[SalesOrder]] = relationship(back_populates="batch")


class SalesOrder(Base):
    __tablename__ = "sales_order"
    __table_args__ = (UniqueConstraint("platform", "platform_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(ForeignKey("platform_setting.platform"))
    platform_order_id: Mapped[str] = mapped_column(String(40))
    order_batch_id: Mapped[int] = mapped_column(ForeignKey("order_batch.id"))
    shop_code: Mapped[str] = mapped_column(ForeignKey("shop.code"), index=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20))
    status_reason: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    so_number: Mapped[str | None] = mapped_column(String(20), index=True)
    do_number: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    batch: Mapped[OrderBatch] = relationship(back_populates="orders")
    shop: Mapped[Shop] = relationship()
    items: Mapped[list[SalesOrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="SalesOrderItem.line_no"
    )


class SalesOrderItem(Base):
    __tablename__ = "sales_order_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id", ondelete="CASCADE"))
    line_no: Mapped[int] = mapped_column(Integer)
    product_name: Mapped[str] = mapped_column(Text)
    variation_name: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(BigInteger)
    unit_subsidy: Mapped[int] = mapped_column(BigInteger, default=0)
    material_number: Mapped[str | None] = mapped_column(String(20))
    sap_name: Mapped[str | None] = mapped_column(Text)

    order: Mapped[SalesOrder] = relationship(back_populates="items")


class SkuMapping(Base):
    __tablename__ = "sku_mapping"
    __table_args__ = (UniqueConstraint("platform", "product_key", "variation_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(ForeignKey("platform_setting.platform"))
    product_key: Mapped[str] = mapped_column(Text)
    variation_key: Mapped[str] = mapped_column(Text)
    product_name: Mapped[str] = mapped_column(Text)
    variation_name: Mapped[str] = mapped_column(Text)
    material_number: Mapped[str] = mapped_column(String(20))
    sap_name: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CustomerInfo(Base):
    """Customer name and address per platform order; independent of sales_order (Lazada)."""

    __tablename__ = "customer_info"
    __table_args__ = (UniqueConstraint("platform", "platform_order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(ForeignKey("platform_setting.platform"))
    platform_order_id: Mapped[str] = mapped_column(String(40))
    customer_name: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    # One of the 34 provinces, read from the address; NULL when the address names none of them.
    province: Mapped[str | None] = mapped_column(String(30))
    # Folded last part of the address (domain.provinces.place_key), looked up in province_alias.
    place_key: Mapped[str | None] = mapped_column(String(100))
    # Who wrote the address: 'file' (order file), 'label' (shipping label), 'admin'; NULL = unknown.
    address_source: Mapped[str | None] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProvinceAlias(Base):
    """A raw place name (pre-merger province, city, district) and the province it belongs to.
    `raw_key` is the name folded by domain.provinces.fold_key."""

    __tablename__ = "province_alias"

    raw_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    province: Mapped[str] = mapped_column(String(30))
    updated_by: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HistorySaleLine(Base):
    """One line of the accountants' Shop Online history file (orders before the system took
    over). Read-only reporting data: nothing here is posted anywhere."""

    __tablename__ = "history_sale_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[date] = mapped_column(Date, index=True)  # first day of the file's month/year
    ordered_on: Mapped[date | None] = mapped_column(Date)
    shop_code: Mapped[str] = mapped_column(ForeignKey("shop.code"), index=True)
    customer_name: Mapped[str | None] = mapped_column(Text)
    customer_phone: Mapped[str | None] = mapped_column(String(30))
    city_raw: Mapped[str | None] = mapped_column(Text)
    city_key: Mapped[str | None] = mapped_column(String(100))  # fold_key(city_raw)
    item_name: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str | None] = mapped_column(Text)
    variation: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    customer_paid: Mapped[int] = mapped_column(BigInteger)
    unit_price: Mapped[int | None] = mapped_column(BigInteger)
    seller_discount: Mapped[int | None] = mapped_column(BigInteger)
    shipping_fee: Mapped[int | None] = mapped_column(BigInteger)
    order_key: Mapped[str] = mapped_column(String(64), index=True)
    line_key: Mapped[str] = mapped_column(String(64), unique=True)
    source_row: Mapped[int] = mapped_column(Integer)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id"), index=True)


class EventLog(Base):
    """Append-only audit trail. Never store customer names or addresses here."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(40))
    platform: Mapped[str | None] = mapped_column(String(20))
    platform_order_id: Mapped[str | None] = mapped_column(String(40), index=True)
    detail: Mapped[str | None] = mapped_column(Text)


class SapSoRef(Base):
    """A sales order as seen in zrsd001: SO number and its PO No (platform order id)."""

    __tablename__ = "sap_so_ref"

    so_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    po_no: Mapped[str] = mapped_column(String(40), index=True)
    sold_to: Mapped[str] = mapped_column(String(20))
    doc_date: Mapped[date] = mapped_column(Date)
    net_value_incl: Mapped[int] = mapped_column(BigInteger)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[SapSoRefItem]] = relationship(
        back_populates="so_ref", cascade="all, delete-orphan", order_by="SapSoRefItem.item_no"
    )


class SapSoRefItem(Base):
    __tablename__ = "sap_so_ref_item"

    so_number: Mapped[str] = mapped_column(
        ForeignKey("sap_so_ref.so_number", ondelete="CASCADE"), primary_key=True
    )
    item_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_number: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Numeric(15, 3))
    net_value_incl: Mapped[int] = mapped_column(BigInteger)

    so_ref: Mapped[SapSoRef] = relationship(back_populates="items")


class SapTaxInvoice(Base):
    """The tax invoice of one platform delivery, as seen in zrsd003 (one invoice per DO)."""

    __tablename__ = "sap_tax_invoice"

    delivery: Mapped[str] = mapped_column(String(20), primary_key=True)
    tax_invoice_doc: Mapped[str] = mapped_column(String(20))
    billing_doc: Mapped[str] = mapped_column(String(20))
    billing_date: Mapped[date] = mapped_column(Date)
    bill_to: Mapped[str] = mapped_column(String(20))
    # Invoice totals before tax and of tax; NULL for invoices read from a file without the columns.
    net_value_vnd: Mapped[int | None] = mapped_column(BigInteger)
    tax_vnd: Mapped[int | None] = mapped_column(BigInteger)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlatformSettlement(Base):
    """One settlement transaction of a platform order (money the platform paid out, signed)."""

    __tablename__ = "platform_settlement"
    __table_args__ = (
        UniqueConstraint("platform", "line_key"),
        Index("ix_platform_settlement_order", "platform", "platform_order_id"),
        CheckConstraint(
            "(source = 'file' AND import_batch_id IS NOT NULL)"
            " OR (source = 'manual' AND entered_by IS NOT NULL)",
            name="ck_platform_settlement_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    platform_order_id: Mapped[str] = mapped_column(String(40))
    line_key: Mapped[str] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(BigInteger)
    settled_at: Mapped[datetime] = mapped_column(DateTime)
    # 'file' rows come from a settlement file (import_batch_id set); 'manual' rows are typed in
    # for Lazada, one per order with line_key 'manual:<order id>' (entered_by set).
    source: Mapped[str] = mapped_column(String(10), default="file", server_default="file")
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))
    entered_by: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SapJob(Base):
    """One unit of SAP work for the robot. The target system is part of every job."""

    __tablename__ = "sap_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    target_system: Mapped[str] = mapped_column(String(10))
    target_client: Mapped[str] = mapped_column(String(3))
    dedupe_key: Mapped[str] = mapped_column(String(120))
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(15), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    evidence_path: Mapped[str | None] = mapped_column(String(500))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id"))


class RobotControl(Base):
    """Single row (id=1): stop switch and consecutive failure counter of the robot."""

    __tablename__ = "robot_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    paused: Mapped[bool] = mapped_column(default=False)
    paused_reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str | None] = mapped_column(String(50))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    # Written by the robot on every loop so the web can tell whether it is alive.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    robot_host: Mapped[str | None] = mapped_column(String(100))
    # JSON list of the SAP Logon entry names on the robot machine.
    saplogon_entries: Mapped[str | None] = mapped_column(Text)
    # NULL = the robot has not reported yet. The password itself never reaches the database.
    password_present: Mapped[bool | None] = mapped_column(Boolean)


class SapSetting(Base):
    """Single row (id=1): which SAP system the robot works on and how it logs on.

    A NULL column falls back to the environment variable; the password is not stored here.
    """

    __tablename__ = "sap_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    system: Mapped[str | None] = mapped_column(String(10))
    client: Mapped[str | None] = mapped_column(String(3))
    connection: Mapped[str | None] = mapped_column(String(100))
    sap_user: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str | None] = mapped_column(String(5))
    max_failures: Mapped[int | None] = mapped_column(Integer)
    evidence_keep_days: Mapped[int | None] = mapped_column(Integer)
    # The system and client of the last successful connection check.
    verified_system: Mapped[str | None] = mapped_column(String(10))
    verified_client: Mapped[str | None] = mapped_column(String(3))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_by: Mapped[str | None] = mapped_column(String(50))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountingRun(Base):
    """One export for the accountants: every undelivered-to-accounting DO of all platforms."""

    __tablename__ = "accounting_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'FINALIZED', 'CANCELLED', 'REVOKED')",
            name="ck_accounting_run_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(12))
    created_by: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finalized_by: Mapped[str | None] = mapped_column(String(50))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What the person confirmed at finalization: missing platform/day pairs and orders without DO.
    missing_note: Mapped[str | None] = mapped_column(Text)
    generated_file_id: Mapped[int | None] = mapped_column(ForeignKey("generated_file.id"))


class AccountingRunRead(Base):
    """One platform and goods issue day that the run reads from SAP."""

    __tablename__ = "accounting_run_read"
    __table_args__ = (UniqueConstraint("run_id", "platform", "gi_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("accounting_run.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(ForeignKey("platform_setting.platform"))
    gi_date: Mapped[date] = mapped_column(Date)
    sap_job_id: Mapped[int | None] = mapped_column(ForeignKey("sap_job.id"))


class AccountingRunSource(Base):
    """A zrsd004 file uploaded by hand and attached to a run."""

    __tablename__ = "accounting_run_source"

    run_id: Mapped[int] = mapped_column(
        ForeignKey("accounting_run.id", ondelete="CASCADE"), primary_key=True
    )
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batch.id"), primary_key=True)
    # JSON list of "sold-to|YYYY-MM-DD" for the customers and goods issue days the file covers.
    coverage: Mapped[str] = mapped_column(Text, default="[]")


class AccountingSentDelivery(Base):
    """A delivery already sent to accounting. run_id is NULL for the opening ledger."""

    __tablename__ = "accounting_sent_delivery"

    delivery: Mapped[str] = mapped_column(String(20), primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("accounting_run.id"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountingBaseline(Base):
    """Single row (id=1): a delivery whose goods issue date is on or before it counts as sent."""

    __tablename__ = "accounting_baseline"
    __table_args__ = (CheckConstraint("id = 1", name="ck_accounting_baseline_single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cutoff_date: Mapped[date] = mapped_column(Date)


class ReportItemName(Base):
    """How a material is written in the Shop Online history file (itemName, size, variation)."""

    __tablename__ = "report_item_name"
    __table_args__ = (
        CheckConstraint(
            "item_name <> '' AND size <> '' AND variation <> ''",
            name="ck_report_item_name_filled",
        ),
    )

    material_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    item_name: Mapped[str] = mapped_column(Text)
    size: Mapped[str] = mapped_column(Text)
    variation: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SalesHistoryFileOrder(Base):
    """An order contained in one downloaded Shop Online history file."""

    __tablename__ = "sales_history_file_order"

    generated_file_id: Mapped[int] = mapped_column(
        ForeignKey("generated_file.id"), primary_key=True
    )
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"), primary_key=True)


class SalesHistoryExported(Base):
    """An order confirmed as pasted into the history file; at most once per order."""

    __tablename__ = "sales_history_exported"

    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"), primary_key=True)
    generated_file_id: Mapped[int] = mapped_column(ForeignKey("generated_file.id"), index=True)
    confirmed_by: Mapped[str] = mapped_column(String(50))
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InvoiceItemText(Base):
    """How a material is written on the tax invoice (read from the invoice PDF or typed in)."""

    __tablename__ = "invoice_item_text"

    material_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    invoice_name: Mapped[str] = mapped_column(Text)
    invoice_unit: Mapped[str] = mapped_column(Text)
    stock_unit: Mapped[str] = mapped_column(String(10), server_default="PC")
    source: Mapped[str] = mapped_column(String(40))  # the invoice number read, or "manual"
    updated_by: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentCounter(Base):
    """The next number of a document type for one year; issuing locks the row."""

    __tablename__ = "document_counter"

    doc_type: Mapped[str] = mapped_column(String(30), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer)


class SalesReturn(Base):
    """An issued invoice adjustment for a delivered order. Holds a snapshot of the invoice and
    the buyer, so the two files can be produced again after customer_info is purged."""

    __tablename__ = "sales_return"
    __table_args__ = (
        UniqueConstraint("doc_year", "doc_seq"),
        CheckConstraint("reason_kind IN ('CANCEL', 'RETURN')", name="ck_sales_return_reason"),
        CheckConstraint("status IN ('ISSUED', 'VOID')", name="ck_sales_return_status"),
        Index(
            "uq_sales_return_one_issued",
            "sales_order_id",
            unique=True,
            postgresql_where=text("status = 'ISSUED'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"))
    reason_kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="ISSUED")
    doc_year: Mapped[int] = mapped_column(Integer)
    doc_seq: Mapped[int] = mapped_column(Integer)
    doc_no: Mapped[str] = mapped_column(String(60), unique=True)
    full_return: Mapped[bool] = mapped_column(Boolean)
    delivery: Mapped[str] = mapped_column(String(20))
    tax_invoice_doc: Mapped[str] = mapped_column(String(20))
    invoice_symbol: Mapped[str] = mapped_column(String(20))
    billing_date: Mapped[date] = mapped_column(Date)
    invoice_net: Mapped[int] = mapped_column(BigInteger)
    invoice_tax: Mapped[int] = mapped_column(BigInteger)
    vat_rate: Mapped[int] = mapped_column(Integer)
    returned_net: Mapped[int] = mapped_column(BigInteger)
    returned_tax: Mapped[int] = mapped_column(BigInteger)
    buyer_name: Mapped[str] = mapped_column(Text)
    buyer_address: Mapped[str] = mapped_column(Text)
    platform_name: Mapped[str] = mapped_column(String(100))
    docx_file_id: Mapped[int | None] = mapped_column(ForeignKey("generated_file.id"))
    xlsx_file_id: Mapped[int | None] = mapped_column(ForeignKey("generated_file.id"))
    issued_by: Mapped[str] = mapped_column(String(50))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    voided_by: Mapped[str | None] = mapped_column(String(50))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped[SalesOrder] = relationship()
    lines: Mapped[list[SalesReturnLine]] = relationship(
        back_populates="sales_return",
        cascade="all, delete-orphan",
        order_by="SalesReturnLine.line_no",
    )
    sale_lines: Mapped[list[SalesReturnSaleLine]] = relationship(
        cascade="all, delete-orphan", order_by="SalesReturnSaleLine.sales_order_item_id"
    )


class SalesReturnLine(Base):
    """Every invoice line, returned or not: the "before adjustment" table is drawn from these."""

    __tablename__ = "sales_return_line"

    return_id: Mapped[int] = mapped_column(
        ForeignKey("sales_return.id", ondelete="CASCADE"), primary_key=True
    )
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    so_item_no: Mapped[int] = mapped_column(Integer)
    material_number: Mapped[str] = mapped_column(String(20))
    sap_name: Mapped[str] = mapped_column(Text)
    invoice_name: Mapped[str] = mapped_column(Text)
    invoice_unit: Mapped[str] = mapped_column(Text)
    stock_unit: Mapped[str] = mapped_column(String(10))
    invoice_qty: Mapped[float] = mapped_column(Numeric(15, 3))
    return_qty: Mapped[float] = mapped_column(Numeric(15, 3))
    unit_price: Mapped[int] = mapped_column(BigInteger)
    amount_before: Mapped[int] = mapped_column(BigInteger)
    amount_returned: Mapped[int] = mapped_column(BigInteger)

    sales_return: Mapped[SalesReturn] = relationship(back_populates="lines")


class SalesReturnSaleLine(Base):
    """What a return takes off one platform order line, at the marketplace price (unit price less
    the platform subsidy), so the Shop Online file and the reports subtract the same figures."""

    __tablename__ = "sales_return_sale_line"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_return_sale_line_quantity"),
        CheckConstraint("customer_paid >= 0", name="ck_sales_return_sale_line_paid"),
    )

    return_id: Mapped[int] = mapped_column(
        ForeignKey("sales_return.id", ondelete="CASCADE"), primary_key=True
    )
    sales_order_item_id: Mapped[int] = mapped_column(
        ForeignKey("sales_order_item.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    customer_paid: Mapped[int] = mapped_column(BigInteger)

    item: Mapped[SalesOrderItem] = relationship()


class SalesHistoryFileReturn(Base):
    """A return's rows in one downloaded Shop Online file: ISSUE are the negative rows, VOID the
    rows that reverse them after the return was cancelled."""

    __tablename__ = "sales_history_file_return"
    __table_args__ = (
        CheckConstraint("kind IN ('ISSUE', 'VOID')", name="ck_sales_history_file_return_kind"),
    )

    generated_file_id: Mapped[int] = mapped_column(
        ForeignKey("generated_file.id"), primary_key=True
    )
    return_id: Mapped[int] = mapped_column(ForeignKey("sales_return.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)


class SalesReturnHistoryExported(Base):
    """A return's rows confirmed as pasted into the history file; at most once per kind."""

    __tablename__ = "sales_return_history_exported"
    __table_args__ = (
        CheckConstraint("kind IN ('ISSUE', 'VOID')", name="ck_sales_return_history_exported_kind"),
    )

    return_id: Mapped[int] = mapped_column(ForeignKey("sales_return.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)
    generated_file_id: Mapped[int] = mapped_column(ForeignKey("generated_file.id"), index=True)
    confirmed_by: Mapped[str] = mapped_column(String(50))
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# Schema ops: operational records that must survive a restore of schema public on the same
# machine. Migrations touching these tables are idempotent (see migrations/versions/0010_backup.py).


class SystemState(Base):
    """Single row (id=1). session_epoch goes up after each restore so everybody logs in again."""

    __tablename__ = "system_state"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    session_epoch: Mapped[int] = mapped_column(Integer, default=0)


class BackupSettings(Base):
    """Single row (id=1): backup schedule and how many backups each place keeps.

    full_weekday follows Python's date.weekday(): Monday is 0, Friday is 4.
    """

    __tablename__ = "backup_settings"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    db_time: Mapped[time] = mapped_column(Time, default=time(16, 30))
    full_weekday: Mapped[int] = mapped_column(Integer, default=4)
    full_time: Mapped[time] = mapped_column(Time, default=time(16, 30))
    keep_db: Mapped[int] = mapped_column(Integer, default=15)
    keep_app: Mapped[int] = mapped_column(Integer, default=15)
    full_max_days: Mapped[int] = mapped_column(Integer, default=30)
    drive_on_schedule: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_by: Mapped[str | None] = mapped_column(String(50))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackupRun(Base):
    """One backup attempt (failed ones too), so the list doubles as the backup log."""

    __tablename__ = "backup_run"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    # schedule | manual | deploy | safety | migration | upload | drive_found
    source: Mapped[str] = mapped_column(String(20))
    actor: Mapped[str] = mapped_column(String(50))
    file_name: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # running | ok | partial | failed | interrupted | rotated | deleted
    local_status: Mapped[str] = mapped_column(String(20), default="running")
    local_error: Mapped[str | None] = mapped_column(Text)
    drive_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    # None (not asked) | uploading | ok | failed | not_connected | rotated | deleted
    drive_status: Mapped[str | None] = mapped_column(String(20))
    drive_file_id: Mapped[str | None] = mapped_column(String(200))
    drive_error: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verify_result: Mapped[str | None] = mapped_column(Text)
    deleted_by: Mapped[str | None] = mapped_column(String(50))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BackupRequest(Base):
    """The one queue for every background backup action asked for on the web."""

    __tablename__ = "backup_request"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    # backup | retry_drive | drill | verify | restore
    action: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str | None] = mapped_column(String(10))
    target_run_id: Mapped[int | None] = mapped_column(ForeignKey("ops.backup_run.id"))
    to_drive: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_by: Mapped[str] = mapped_column(String(50))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # pending | running | done | failed | rolled_back | expired | interrupted
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
    safety_run_id: Mapped[int | None] = mapped_column(ForeignKey("ops.backup_run.id"))


class DriveConnection(Base):
    """Single row (id=1): non-secret state of the Google Drive connection.

    status: disconnected | connected | error. device_code and the fields next to it exist only
    while a device flow waits for the person to approve on google.com/device.
    """

    __tablename__ = "drive_connection"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str | None] = mapped_column(String(200))
    folder_id: Mapped[str | None] = mapped_column(String(200))
    account_email: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="disconnected")
    last_error: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_code: Mapped[str | None] = mapped_column(String(500))
    user_code: Mapped[str | None] = mapped_column(String(50))
    verification_url: Mapped[str | None] = mapped_column(String(200))
    device_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poll_interval: Mapped[int | None] = mapped_column(Integer)
    changed_by: Mapped[str | None] = mapped_column(String(50))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
