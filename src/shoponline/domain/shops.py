"""Which shop an order belongs to: the catalog (table shop) and the choices made against it."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.db.models import ImportBatch, SalesOrder, Shop


class ShopRefused(ValueError):
    """The chosen shop cannot be used; the message says why."""


def active_shops(session: Session, platform: str | None = None) -> list[Shop]:
    stmt = select(Shop).where(Shop.active)
    if platform is not None:
        stmt = stmt.where(Shop.platform == platform)
    return list(session.scalars(stmt.order_by(Shop.platform, Shop.sort_order, Shop.code)))


def default_shop_code(session: Session, platform: str) -> str | None:
    """The shop to preselect for a platform: its only active shop; with several, the shop of the
    platform's latest upload when that shop is still active; otherwise the first active one."""
    shops = active_shops(session, platform)
    if not shops:
        return None
    if len(shops) == 1:
        return shops[0].code
    latest = session.scalar(
        select(ImportBatch.shop_code)
        .where(ImportBatch.platform == platform, ImportBatch.shop_code.is_not(None))
        .order_by(ImportBatch.id.desc())
        .limit(1)
    )
    return latest if latest in {s.code for s in shops} else shops[0].code


def require_choice(session: Session, platform: str, shop_code: str | None) -> Shop:
    """The active shop of this platform, or ShopRefused."""
    shop = session.get(Shop, shop_code) if shop_code else None
    if shop is None:
        raise ShopRefused("Chưa chọn shop")
    if shop.platform != platform:
        raise ShopRefused(f"Shop {shop.code} không thuộc sàn {platform}")
    if not shop.active:
        raise ShopRefused(f"Shop {shop.code} đang tắt")
    return shop


def default_shop(session: Session, platform: str) -> Shop:
    """The shop for an order created without a choice (scripts, tests); raises when the platform
    has no active shop."""
    code = default_shop_code(session, platform)
    if code is None:
        raise ShopRefused(f"Sàn {platform} chưa có shop đang bán")
    return session.get(Shop, code)


def has_orders(session: Session, code: str) -> bool:
    return (
        session.scalar(select(SalesOrder.id).where(SalesOrder.shop_code == code).limit(1))
        is not None
    )
