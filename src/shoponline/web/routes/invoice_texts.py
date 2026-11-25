"""How each material is written on the tax invoice: the master the return documents read."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, InvoiceItemText, SkuMapping
from shoponline.domain import states
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()
FIELDS = ("material_number", "invoice_name", "invoice_unit", "stock_unit")
VALUES = FIELDS[1:]
DEFAULT_STOCK_UNIT = "PC"
MAX_TEXT = 200


def _rows(db: Session, entered: dict[str, dict] | None = None) -> list[dict]:
    """Every material of the SAP mapping or the master, unsaved ones first."""
    sap_names = dict(
        db.execute(
            select(SkuMapping.material_number, func.min(SkuMapping.sap_name)).group_by(
                SkuMapping.material_number
            )
        ).all()
    )
    saved = {r.material_number: r for r in db.scalars(select(InvoiceItemText))}
    rows = []
    for material in sorted(set(sap_names) | set(saved)):
        record = saved.get(material)
        rows.append(
            {
                "material_number": material,
                "sap_name": sap_names.get(material, ""),
                "saved": record,
                "invoice_name": record.invoice_name if record else "",
                "invoice_unit": record.invoice_unit if record else "",
                "stock_unit": record.stock_unit if record else DEFAULT_STOCK_UNIT,
                "error": "",
                **(entered or {}).get(material, {}),
            }
        )
    rows.sort(key=lambda r: r["saved"] is not None)  # stable: material order inside each group
    return rows


def _page(request: Request, db: Session, user: AppUser, missing: bool, entered=None):
    rows = _rows(db, entered)
    unsaved = sum(1 for r in rows if r["saved"] is None)
    if missing:
        rows = [r for r in rows if r["saved"] is None or r["error"]]
    return render(request, "invoice_texts.html", user, rows=rows, missing=missing, unsaved=unsaved)


@router.get("/invoice-texts")
def list_invoice_texts(
    request: Request,
    missing: bool = False,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    return _page(request, db, user, missing)


def _problem(values: dict[str, str]) -> str:
    if any(len(v) > MAX_TEXT for v in values.values()):
        return f"Tối đa {MAX_TEXT} ký tự mỗi ô"
    if any(c < " " or c == "\x7f" for v in values.values() for c in v):
        return "Có ký tự điều khiển"
    return ""


@router.post("/invoice-texts")
async def save_invoice_texts(
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Save every row whose name and unit are filled; rows left empty are skipped.

    All-or-nothing, like /report-names: a row with only one of the two filled rejects the whole
    save, and the page comes back with every typed value kept and the bad rows marked.
    """
    form = await request.form()
    missing = form.get("missing") == "true"
    back = f"/invoice-texts{'?missing=true' if missing else ''}"
    columns = [[str(v).strip() for v in form.getlist(name)] for name in FIELDS]
    if len({len(c) for c in columns}) != 1:
        flash(request, "Dữ liệu gửi lên không hợp lệ, hãy tải lại trang.", "error")
        return redirect(back)
    entered = {
        values[0]: dict(zip(FIELDS, values, strict=True), error="")
        for values in zip(*columns, strict=True)
    }
    known = set(db.scalars(select(SkuMapping.material_number).distinct()))
    saved = {r.material_number: r for r in db.scalars(select(InvoiceItemText))}
    known |= set(saved)
    filled = []
    for material, row in entered.items():
        row["stock_unit"] = row["stock_unit"] or DEFAULT_STOCK_UNIT
        if material not in known:
            row["error"] = "Mã vật tư không có trong ánh xạ SAP"
        elif row["invoice_name"] and row["invoice_unit"]:
            row["error"] = _problem({f: row[f] for f in VALUES})
            if not row["error"]:
                filled.append(row)
        elif row["invoice_name"] or row["invoice_unit"]:
            row["error"] = "Cần đủ tên hàng và đơn vị tính trên hóa đơn"
        elif material in saved:
            row["error"] = "Không thể xóa trống một dòng đã lưu"
    failed = sum(1 for row in entered.values() if row["error"])
    if failed:
        unknown = [m for m in entered if m not in known]
        flash(
            request,
            f"{failed} dòng sai nên chưa lưu dòng nào. Sửa các dòng báo đỏ rồi bấm lưu lại."
            + (f"\nMã vật tư không có trong ánh xạ SAP: {', '.join(unknown)}" if unknown else ""),
            "error",
        )
        return _page(request, db, user, missing, entered)
    changed = []
    for row in filled:
        record = saved.get(row["material_number"])
        if record is None:
            db.add(
                InvoiceItemText(
                    **{f: row[f] for f in FIELDS}, source="manual", updated_by=user.username
                )
            )
        elif any(getattr(record, f) != row[f] for f in VALUES):
            for f in VALUES:
                setattr(record, f, row[f])
            record.source, record.updated_by = "manual", user.username
        else:
            continue
        changed.append(row["material_number"])
    if changed:
        states.log_event(
            db, user.username, "invoice_texts_saved", detail={"materials": sorted(changed)}
        )
    db.commit()
    flash(
        request,
        f"Đã lưu {len(changed)} tên trên hóa đơn ({len(filled) - len(changed)} dòng không đổi).",
    )
    return redirect(back)
