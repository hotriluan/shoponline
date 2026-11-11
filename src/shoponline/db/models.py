"""SQLAlchemy models. Schema changes go through Alembic migrations in migrations/versions."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PlatformSetting(Base):
    __tablename__ = "platform_setting"

    platform: Mapped[str] = mapped_column(String(20), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(50))
    sap_customer: Mapped[str] = mapped_column(String(20), unique=True)
    mode: Mapped[str] = mapped_column(String(10), default="manual")


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


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
