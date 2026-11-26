from shoponline.returns import flags
from tests.returns import factory


def test_each_kind_of_issued_return_gets_its_label(db):
    cancelled = factory.delivered_order(db, "261115CANCEL01")
    returned = factory.delivered_order(db, "261115RETURN01", texts=False)
    partly = factory.delivered_order(db, "261115PARTLY01", texts=False)
    plain = factory.delivered_order(db, "261115PLAIN001", texts=False)
    factory.sales_return(db, cancelled, year=2026, seq=80)
    factory.sales_return(db, returned, year=2026, seq=81).reason_kind = "RETURN"
    factory.sales_return(db, partly, year=2026, seq=82).full_return = False
    db.flush()

    found = flags.of(db, [cancelled.id, returned.id, partly.id, plain.id])
    assert {k: v.label for k, v in found.items()} == {
        cancelled.id: "Hủy sau HĐ",
        returned.id: "Trả hàng",
        partly.id: "Trả một phần",
    }
    assert found[cancelled.id].doc_no.startswith("080/")


def test_a_void_return_gives_no_label(db):
    order = factory.delivered_order(db)
    factory.sales_return(db, order, year=2026, seq=80, status="VOID")
    assert flags.of(db, [order.id]) == {}
    assert flags.of(db, []) == {}
