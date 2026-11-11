from datetime import date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from shoponline.db.models import CustomerInfo, OrderBatch, SalesOrder, SkuMapping
from shoponline.domain import states


def _batch(db):
    batch = OrderBatch(
        platform="SHOPEE", processing_date=date(2026, 11, 11), gi_date=date(2026, 11, 12)
    )
    db.add(batch)
    db.flush()
    return batch


def _order(batch, order_id="A1", status=states.READY):
    return SalesOrder(
        platform="SHOPEE",
        platform_order_id=order_id,
        order_batch_id=batch.id,
        ordered_at=datetime(2026, 11, 11, 8),
        status=status,
    )


def test_one_row_per_platform_order(db):
    batch = _batch(db)
    db.add(_order(batch))
    db.flush()
    db.add(_order(batch))
    with pytest.raises(IntegrityError):
        db.flush()


def test_status_must_be_known(db):
    batch = _batch(db)
    db.add(_order(batch, status="WHATEVER"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_mapping_unique_per_platform_key(db):
    common = dict(
        product_key="P",
        variation_key="V",
        product_name="P",
        variation_name="V",
        material_number="1",
        sap_name="S",
        updated_by="t",
    )
    db.add(SkuMapping(platform="SHOPEE", **common))
    db.add(SkuMapping(platform="TIKTOK", **common))
    db.flush()
    db.add(SkuMapping(platform="SHOPEE", **common))
    with pytest.raises(IntegrityError):
        db.flush()


def test_customer_unique_per_platform_order(db):
    db.add(CustomerInfo(platform="LAZADA", platform_order_id="533904380882298"))
    db.flush()
    db.add(CustomerInfo(platform="LAZADA", platform_order_id="533904380882298"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_transition_rejects_moving_back(db):
    batch = _batch(db)
    order = _order(batch, status=states.SO_LINKED)
    db.add(order)
    db.flush()
    with pytest.raises(states.InvalidTransition):
        states.transition(db, order, states.READY, "test")
