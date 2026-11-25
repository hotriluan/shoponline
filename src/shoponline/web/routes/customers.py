import asyncio

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, CustomerInfo, OrderBatch, PlatformSetting, SalesOrder
from shoponline.domain.provinces import place_key
from shoponline.domain.report_names import province_of
from shoponline.importers.customer_labels import apply_labels
from shoponline.importers.excel_table import FileRejected
from shoponline.importers.shipping_label_pdf import MAX_BYTES, Label, read_label_pdf
from shoponline.web.app import (
    autosave_reply,
    current_user,
    flash,
    get_db,
    is_autosave,
    redirect,
    render,
    require_admin,
)
from shoponline.web.pagination import paginate

router = APIRouter()

MAX_LABEL_FILES = 10
LABEL_PDF_SECONDS = 60  # a 500-page file reads in about 35 seconds


@router.get("/customers")
def list_customers(
    request: Request,
    batch_id: str = "",  # the filter's "no batch" option submits an empty value
    platform: str | None = None,
    missing: bool = False,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    batch = db.get(OrderBatch, int(batch_id)) if batch_id.strip().isdigit() else None
    page = None  # only the per-platform list is paged on the server
    if batch is not None:
        order_ids = [o.platform_order_id for o in sorted(batch.orders, key=lambda o: o.ordered_at)]
        found = {
            c.platform_order_id: c
            for c in db.scalars(
                select(CustomerInfo).where(
                    CustomerInfo.platform == batch.platform,
                    CustomerInfo.platform_order_id.in_(order_ids),
                )
            )
        }
        rows = [
            found.get(oid) or CustomerInfo(platform=batch.platform, platform_order_id=oid)
            for oid in order_ids
        ]
        platform = batch.platform
    else:
        platform = platform or "LAZADA"
        stmt = (
            select(CustomerInfo)
            .where(CustomerInfo.platform == platform)
            .order_by(CustomerInfo.updated_at.desc(), CustomerInfo.id.desc())
        )
        if missing:
            stmt = stmt.where(
                or_(
                    func.coalesce(CustomerInfo.customer_name, "") == "",
                    func.coalesce(CustomerInfo.address, "") == "",
                )
            )
        page = paginate(
            request,
            db,
            stmt,
            CustomerInfo.platform_order_id,
            CustomerInfo.customer_name,
            CustomerInfo.address,
        )
        rows = page.items
    if batch is not None and missing:
        rows = [r for r in rows if not r.customer_name or not r.address]
    batches = db.scalars(
        select(OrderBatch).order_by(OrderBatch.processing_date.desc()).limit(30)
    ).all()
    platforms = list(
        db.scalars(select(PlatformSetting.platform).order_by(PlatformSetting.platform))
    )
    return render(
        request,
        "customers.html",
        user,
        rows=rows,
        page=page,
        batch=batch,
        batches=batches,
        platform=platform,
        platforms=platforms,
        missing=missing,
    )


@router.post("/customers/save")
def save_customer(
    request: Request,
    platform: str = Form(...),
    platform_order_id: str = Form(...),
    customer_name: str = Form(""),
    address: str = Form(""),
    return_to: str = Form("/customers"),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    order_id = platform_order_id.strip()
    if not order_id or db.get(PlatformSetting, platform) is None:
        if is_autosave(request):
            return autosave_reply("Cần sàn và mã đơn.", ok=False)
        flash(request, "Cần sàn và mã đơn.", "error")
        return redirect(_safe(return_to))
    info = db.scalar(
        select(CustomerInfo).where(
            CustomerInfo.platform == platform, CustomerInfo.platform_order_id == order_id
        )
    )
    if info is None:
        info = CustomerInfo(platform=platform, platform_order_id=order_id)
        db.add(info)
    info.customer_name = customer_name.strip() or None
    new_address = address.strip() or None
    # The autosave sends the whole row, so editing only the name must leave the source alone.
    if new_address != info.address:
        info.address = new_address
        info.address_source = "admin" if new_address else None
        info.province = province_of(new_address)
        info.place_key = place_key(new_address)
    has_order = db.scalar(
        select(SalesOrder.id).where(
            SalesOrder.platform == platform, SalesOrder.platform_order_id == order_id
        )
    )
    db.commit()
    note = "" if has_order else " (chưa có đơn nào mang mã này)"
    if is_autosave(request):
        return autosave_reply(f"Đã lưu{note}")
    flash(request, f"Đã lưu khách hàng của đơn {order_id}{note}.")
    return redirect(_safe(return_to))


@router.post("/customers/labels")
async def upload_labels(
    request: Request,
    pdfs: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Read the recipients of shipping label PDFs into customer_info. The PDFs are read in memory
    and thrown away; names and addresses are never put into a message or a log."""
    files = [f for f in pdfs if f.filename]
    labels: list[Label] = []
    unreadable: list[str] = []
    try:
        refusal = _refuse_label_upload(request, files)
        if refusal is None:
            refusal = await _read_all_labels(files, labels, unreadable)
    finally:
        for f in pdfs:
            await f.close()  # the temporary copy of a large upload goes now
    if refusal is not None:
        flash(request, refusal, "error")
        return redirect("/customers")
    result = apply_labels(db, labels)
    db.commit()
    summary = (
        f"Đã ghi {result.written} đơn, giữ nguyên {result.unchanged}"
        + (f", {len(result.pending)} đơn cần xác nhận" if result.pending else "")
        + (f", {result.without_order} đơn chưa có trong hệ thống" if result.without_order else "")
        + (f", bỏ qua {result.skipped} nhãn của sàn lạ" if result.skipped else "")
        + "."
        + (f" Trang không đọc được: {'; '.join(unreadable)}." if unreadable else "")
    )
    flash(request, summary, "warn" if unreadable or result.pending else "info")
    if result.pending:
        return render(request, "customer_labels_confirm.html", user, pending=result.pending)
    return redirect("/customers")


def _refuse_label_upload(request: Request, files: list[UploadFile]) -> str | None:
    if not files:
        return "Chưa chọn file PDF nào."
    if len(files) > MAX_LABEL_FILES:
        return f"Mỗi lần tải tối đa {MAX_LABEL_FILES} file."
    announced = request.headers.get("content-length")
    if (
        announced
        and announced.isdigit()
        and int(announced) > MAX_LABEL_FILES * MAX_BYTES + 64 * 1024
    ):
        return f"Tổng dung lượng quá lớn (mỗi file tối đa {MAX_BYTES // 1024 // 1024} MB)."
    return None


async def _read_all_labels(
    files: list[UploadFile], labels: list[Label], unreadable: list[str]
) -> str | None:
    """Reads each file in a worker thread under a time limit. One bad file refuses the whole
    upload, so nothing is half written. Returns the refusal, or None when all files were read."""
    for upload in files:
        data = await upload.read(MAX_BYTES + 1)
        try:
            read = await asyncio.wait_for(
                run_in_threadpool(read_label_pdf, data), timeout=LABEL_PDF_SECONDS
            )
        except TimeoutError:
            return f"Đọc {upload.filename} quá lâu nên đã dừng. Không ghi gì."
        except FileRejected as exc:
            return f"{upload.filename}: {exc} Không ghi gì."
        finally:
            del data
        if not read.labels:
            return f"{upload.filename}: không trang nào là phiếu vận đơn đọc được. Không ghi gì."
        labels.extend(read.labels)
        if read.unreadable:
            pages = ", ".join(str(n) for n in read.unreadable)
            unreadable.append(f"{upload.filename} trang {pages}")
    return None


@router.post("/customers/labels/confirm")
def confirm_labels(
    request: Request,
    pick: list[int] = Form(default=[]),
    platform: list[str] = Form(default=[]),
    order_id: list[str] = Form(default=[]),
    name: list[str] = Form(default=[]),
    address: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Overwrite the orders the admin ticked on the confirmation page with what the label says."""
    if len({len(platform), len(order_id), len(name), len(address)}) != 1:
        flash(request, "Dữ liệu xác nhận không khớp, hãy tải lại file.", "error")
        return redirect("/customers")
    chosen = [
        Label(
            platform[i],
            order_id[i].strip(),
            " ".join(name[i].split()),
            " ".join(address[i].split()),
        )
        for i in sorted(set(pick))
        if 0 <= i < len(platform)
    ]
    labels = [lb for lb in chosen if lb.order_id and lb.name and lb.address]
    result = apply_labels(db, labels, confirmed={(lb.platform, lb.order_id) for lb in labels})
    db.commit()
    flash(request, f"Đã ghi đè {result.written} đơn theo phiếu vận đơn.")
    return redirect("/customers")


def _safe(url: str) -> str:
    """Only allow local redirects."""
    return url if url.startswith("/") and not url.startswith("//") else "/customers"
