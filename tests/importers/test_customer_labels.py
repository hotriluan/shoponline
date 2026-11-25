from sqlalchemy import select

from shoponline.db.models import CustomerInfo, EventLog
from shoponline.importers.customer_labels import apply_labels
from shoponline.importers.shipping_label_pdf import Label

ADDRESS = "12 Đường Thử, Phường Một, Hà Nội, Việt Nam"
OTHER = "99 Đường Khác, Phường Hai, Thành phố Hồ Chí Minh, Việt Nam"


def label(order="A1", name="Nguyễn Thử", address=ADDRESS, platform="SHOPEE", conflicting=False):
    return Label(platform, order, name, address, (1,), conflicting)


def stored(db, order="A1", platform="SHOPEE"):
    return db.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == platform, CustomerInfo.platform_order_id == order
        )
    )


def customer(db, *, name=None, address=None, source=None, order="A1"):
    db.add(
        CustomerInfo(
            platform="SHOPEE",
            platform_order_id=order,
            customer_name=name,
            address=address,
            address_source=source,
        )
    )
    db.flush()


def test_a_new_order_gets_its_name_address_province_and_label_source(db):
    result = apply_labels(db, [label()])

    info = stored(db)
    assert (info.customer_name, info.address) == ("Nguyễn Thử", ADDRESS)
    assert (info.address_source, info.province) == ("label", "Hà Nội")
    assert info.place_key
    assert (result.written, result.unchanged, result.pending) == (1, 0, [])


def test_blank_name_and_address_are_filled(db):
    customer(db)

    apply_labels(db, [label()])

    info = stored(db)
    assert (info.customer_name, info.address, info.address_source) == (
        "Nguyễn Thử",
        ADDRESS,
        "label",
    )


def test_the_same_name_and_address_are_kept_even_when_spaced_differently(db):
    customer(db, name="Nguyễn  Thử ", address=ADDRESS, source="admin")

    result = apply_labels(db, [label()])

    info = stored(db)
    assert info.customer_name == "Nguyễn  Thử " and info.address_source == "admin"
    assert (result.written, result.unchanged, result.pending) == (0, 1, [])


def test_a_different_name_waits_for_the_admin(db):
    customer(db, name="Tên Cũ", address=ADDRESS, source="file")

    result = apply_labels(db, [label()])

    assert stored(db).customer_name == "Tên Cũ"
    [pending] = result.pending
    assert (pending.name_differs, pending.address_differs) == (True, False)
    assert (pending.current_name, pending.label_name) == ("Tên Cũ", "Nguyễn Thử")
    assert result.written == 0


def test_a_different_address_from_the_file_or_an_earlier_label_is_replaced(db):
    customer(db, name="Nguyễn Thử", address="Phường Một, Hà Nội, Việt Nam", source="file")
    customer(db, name="Nguyễn Thử", address=OTHER, source="label", order="A2")

    result = apply_labels(db, [label(), label(order="A2")])

    for order in ("A1", "A2"):
        info = stored(db, order)
        assert (info.address, info.address_source, info.province) == (ADDRESS, "label", "Hà Nội")
    assert (result.written, result.pending) == (2, [])


def test_a_different_address_typed_by_an_admin_or_of_unknown_source_waits(db):
    customer(db, name="Nguyễn Thử", address=OTHER, source="admin")
    customer(db, name="Nguyễn Thử", address=OTHER, source=None, order="A2")

    result = apply_labels(db, [label(), label(order="A2")])

    assert stored(db).address == OTHER and stored(db, "A2").address == OTHER
    assert [(p.order_id, p.address_differs, p.name_differs) for p in result.pending] == [
        ("A1", True, False),
        ("A2", True, False),
    ]
    assert result.written == 0


def test_the_part_that_can_be_written_is_written_and_the_rest_waits(db):
    customer(db, name=None, address=OTHER, source="admin")

    result = apply_labels(db, [label()])

    info = stored(db)
    assert (info.customer_name, info.address, info.address_source) == ("Nguyễn Thử", OTHER, "admin")
    assert result.written == 1
    [pending] = result.pending
    assert (pending.name_differs, pending.address_differs) == (False, True)


def test_confirmed_orders_take_the_label_name_and_address(db):
    customer(db, name="Tên Cũ", address=OTHER, source="admin")
    customer(db, name="Tên Cũ", address=OTHER, source="admin", order="A2")

    result = apply_labels(db, [label(), label(order="A2")], confirmed={("SHOPEE", "A1")})

    info = stored(db)
    assert (info.customer_name, info.address, info.address_source) == (
        "Nguyễn Thử",
        ADDRESS,
        "label",
    )
    assert (stored(db, "A2").customer_name, stored(db, "A2").address) == ("Tên Cũ", OTHER)
    assert [p.order_id for p in result.pending] == ["A2"]


def test_a_label_whose_pages_disagree_waits_and_writes_nothing(db):
    result = apply_labels(db, [label(conflicting=True)])

    assert stored(db) is None or stored(db).customer_name is None
    [pending] = result.pending
    assert pending.conflicting and result.written == 0


def test_the_same_order_in_two_files_that_disagree_waits(db):
    result = apply_labels(db, [label(), label(name="Người Khác")])

    assert [p.conflicting for p in result.pending] == [True]
    assert stored(db) is None or stored(db).customer_name is None


def test_confirming_a_disagreeing_order_writes_it(db):
    apply_labels(db, [label(), label(name="Người Khác")], confirmed={("SHOPEE", "A1")})

    assert stored(db).customer_name == "Nguyễn Thử"


def test_orders_with_no_sales_order_are_counted_and_unknown_platforms_skipped(db):
    result = apply_labels(db, [label(), label(order="B1", platform="NOPE")])

    assert (result.written, result.skipped, result.without_order) == (1, 1, 1)
    assert stored(db, "B1", "NOPE") is None


def test_the_work_writes_no_event_with_a_name_or_address(db):
    apply_labels(db, [label()])

    assert db.scalar(select(EventLog.id)) is None


def test_an_excel_import_after_the_label_keeps_the_label_name_and_address(db, tmp_path):
    from datetime import date

    from shoponline.domain.sku_mapping import upsert_mapping
    from shoponline.importers.order_import import import_orders
    from shoponline.importers.shopee_orders import read_shopee_orders
    from tests.fixtures.build_fixtures import shopee_orders_file, shopee_row

    upsert_mapping(db, "SHOPEE", "Sơn thử A", "Màu 01,1 lít", "100000001", "SAP 100000001", "t")
    apply_labels(db, [label()])
    path = shopee_orders_file(tmp_path / "s.xlsx", [shopee_row("A1")])

    import_orders(db, read_shopee_orders(path), "SHOPEE", date(2026, 11, 11), "test")

    info = stored(db)
    assert (info.customer_name, info.address, info.address_source) == (
        "Nguyễn Thử",
        ADDRESS,
        "label",
    )
