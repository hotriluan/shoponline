import pytest
from sqlalchemy import select
from starlette.datastructures import UploadFile

from shoponline.db.models import CustomerInfo, EventLog
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.shipping_label_pdf import Label, LabelRead

ADDRESS = "12 Đường Thử, Phường Một, Hà Nội, Việt Nam"
OTHER = "99 Đường Khác, Phường Hai, Thành phố Hồ Chí Minh, Việt Nam"
NAME = "Nguyễn Thử"
PDF = b"%PDF-1.4 stand-in"


def files(*names):
    return [("pdfs", (name, PDF, "application/pdf")) for name in names]


def label(order, name=NAME, address=ADDRESS, platform="SHOPEE"):
    return Label(platform, order, name, address, (1,))


@pytest.fixture
def reads(monkeypatch):
    """What each uploaded file 'contains', in upload order; the bytes are not parsed here."""
    queue: list = []
    seen: list[bytes] = []

    def fake(data):
        seen.append(data)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("shoponline.web.routes.customers.read_label_pdf", fake)
    fake.queue = queue
    fake.seen = seen
    return fake


@pytest.fixture
def closed(monkeypatch):
    calls = []
    original = UploadFile.close

    async def spy(self):
        calls.append(self.filename)
        await original(self)

    monkeypatch.setattr(UploadFile, "close", spy)
    return calls


def stored(db, order):
    db.expire_all()
    return db.scalar(select(CustomerInfo).where(CustomerInfo.platform_order_id == order))


def read(*labels, unreadable=()):
    return LabelRead(tuple(labels), tuple(unreadable), len(labels) + len(unreadable))


def flashes(client):
    page = client.get("/customers").text
    return page


def test_a_viewer_cannot_upload_and_sees_no_upload_form(db, login, reads):
    viewer = login("viewer")

    resp = viewer.post("/customers/labels", files=files("a.pdf"), follow_redirects=False)

    assert resp.status_code == 303 and reads.seen == []  # refused: back to a page with a notice
    assert "/customers/labels" not in viewer.get("/customers").text
    assert 'action="/customers/labels"' in login("admin").get("/customers").text


def test_two_files_are_read_and_written_with_a_summary_that_names_no_one(db, login, reads, closed):
    reads.queue += [
        read(label("A1"), unreadable=(3, 7)),
        read(label("T1", platform="TIKTOK", name="user123")),
    ]
    admin = login("admin")

    resp = admin.post("/customers/labels", files=files("shopee.pdf", "tiktok.pdf"))

    assert resp.status_code == 200
    page = resp.text
    assert "Đã ghi 2 đơn" in page and "shopee.pdf trang 3, 7" in page
    assert NAME not in page and ADDRESS not in page and "user123" not in page
    assert (stored(db, "A1").customer_name, stored(db, "A1").address_source) == (NAME, "label")
    assert stored(db, "T1").customer_name == "user123"
    assert set(closed) == {"shopee.pdf", "tiktok.pdf"}


def test_a_second_upload_changes_nothing(db, login, reads):
    reads.queue += [read(label("A1")), read(label("A1"))]
    admin = login("admin")
    admin.post("/customers/labels", files=files("a.pdf"))

    page = admin.post("/customers/labels", files=files("a.pdf")).text

    assert "Đã ghi 0 đơn, giữ nguyên 1" in page


def test_differences_open_the_confirmation_page_and_only_ticked_rows_are_written(db, login, reads):
    for order in ("A1", "A2"):
        db.add(
            CustomerInfo(
                platform="SHOPEE",
                platform_order_id=order,
                customer_name="Tên Cũ",
                address=OTHER,
                address_source="admin",
            )
        )
    db.commit()
    reads.queue.append(read(label("A1"), label("A2")))
    admin = login("admin")

    page = admin.post("/customers/labels", files=files("a.pdf")).text

    assert "Xác nhận khách theo phiếu vận đơn" in page and "2 đơn cần xác nhận" in page
    assert stored(db, "A1").customer_name == "Tên Cũ"

    resp = admin.post(
        "/customers/labels/confirm",
        data={
            "pick": ["0"],
            "platform": ["SHOPEE", "SHOPEE"],
            "order_id": ["A1", "A2"],
            "name": [NAME, NAME],
            "address": [ADDRESS, ADDRESS],
        },
    )

    assert "Đã ghi đè 1 đơn" in resp.text
    assert (stored(db, "A1").customer_name, stored(db, "A1").address) == (NAME, ADDRESS)
    assert (stored(db, "A2").customer_name, stored(db, "A2").address) == ("Tên Cũ", OTHER)


def test_confirming_with_mismatched_lists_writes_nothing(db, login):
    resp = login("admin").post(
        "/customers/labels/confirm",
        data={"pick": ["0"], "platform": ["SHOPEE"], "order_id": [], "name": [NAME]},
    )

    assert "không khớp" in resp.text
    assert stored(db, "A1") is None


def test_confirming_is_for_admins_only(db, login):
    viewer = login("viewer")
    resp = viewer.post(
        "/customers/labels/confirm",
        data={
            "pick": ["0"],
            "platform": ["SHOPEE"],
            "order_id": ["A1"],
            "name": [NAME],
            "address": [ADDRESS],
        },
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert stored(db, "A1") is None


def test_a_rejected_file_refuses_the_whole_upload_and_writes_nothing(db, login, reads, closed):
    reads.queue += [read(label("A1")), FileRejected("Không đọc được phiếu vận đơn: PDF hỏng")]

    page = login("admin").post("/customers/labels", files=files("a.pdf", "bad.pdf")).text

    assert "bad.pdf" in page and "PDF hỏng" in page and "Không ghi gì" in page
    assert stored(db, "A1") is None
    assert set(closed) == {"a.pdf", "bad.pdf"}


def test_a_file_with_no_readable_page_is_refused(db, login, reads):
    reads.queue.append(read(unreadable=(1, 2)))

    page = login("admin").post("/customers/labels", files=files("a.pdf")).text

    assert "không trang nào" in page and "Không ghi gì" in page


def test_a_timeout_stops_the_read_and_writes_nothing(db, login, reads, closed, monkeypatch):
    reads.queue.append(read(label("A1")))

    async def too_slow(awaitable, timeout):
        await awaitable
        raise TimeoutError

    monkeypatch.setattr("shoponline.web.routes.customers.asyncio.wait_for", too_slow)

    page = login("admin").post("/customers/labels", files=files("a.pdf")).text

    assert "quá lâu" in page and stored(db, "A1") is None
    assert set(closed) == {"a.pdf"}


def test_more_than_ten_files_are_refused_before_reading(db, login, reads, closed):
    page = (
        login("admin")
        .post("/customers/labels", files=files(*[f"f{i}.pdf" for i in range(11)]))
        .text
    )

    assert "tối đa 10 file" in page and reads.seen == []
    assert len(set(closed)) == 11


def test_an_oversized_announced_upload_is_refused_before_reading(db, login, reads, monkeypatch):
    monkeypatch.setattr("shoponline.web.routes.customers.MAX_BYTES", 1)
    big = [("pdfs", ("a.pdf", PDF + b"0" * 70_000, "application/pdf"))]

    page = login("admin").post("/customers/labels", files=big).text

    assert "quá lớn" in page and reads.seen == []


def test_no_file_chosen_is_refused(db, login, reads):
    page = login("admin").post("/customers/labels", files=[]).text

    assert "Chưa chọn file" in page


def test_nothing_is_stored_on_disk_and_no_event_carries_a_name(db, login, reads, app):
    reads.queue.append(read(label("A1")))

    login("admin").post("/customers/labels", files=files("a.pdf"))

    data_dir = app.state.settings.data_dir
    assert not data_dir.exists() or not [p for p in data_dir.rglob("*") if p.is_file()]
    assert all(NAME not in (e.detail or "") for e in db.scalars(select(EventLog)))
