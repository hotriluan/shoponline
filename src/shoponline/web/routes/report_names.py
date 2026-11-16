"""Report names (itemName, size, variation) per SAP material for the Shop Online history file."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, ReportItemName, SkuMapping
from shoponline.domain import states
from shoponline.domain.report_names import suggest_report_name
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()
FIELDS = ("material_number", "item_name", "size", "variation")
VALUES = FIELDS[1:]


def _rows(db: Session, entered: dict[str, dict] | None = None) -> list[dict]:
    """Every material in the SAP mapping with its saved names, or a suggestion when unsaved.

    `entered` (by material) refills the form after a rejected save. Unsaved materials first.
    """
    materials = db.execute(
        select(SkuMapping.material_number, func.min(SkuMapping.sap_name))
        .group_by(SkuMapping.material_number)
        .order_by(SkuMapping.material_number)
    ).all()
    pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for material, product, variation in db.execute(
        select(SkuMapping.material_number, SkuMapping.product_name, SkuMapping.variation_name)
    ):
        pairs[material].append((product, variation))
    saved = {r.material_number: r for r in db.scalars(select(ReportItemName))}
    rows = []
    for material, sap_name in materials:
        record = saved.get(material)
        if record is not None:
            values = {f: getattr(record, f) for f in VALUES}
        else:
            suggestion = suggest_report_name(pairs[material])
            values = {f: getattr(suggestion, f) for f in VALUES}
        row = dict(
            material_number=material,
            sap_name=sap_name,
            saved=record,
            error="",
            **values,
        )
        if entered and material in entered:
            row.update(entered[material])
        rows.append(row)
    rows.sort(key=lambda r: r["saved"] is not None)  # stable: material order inside each group
    return rows


def _page(request: Request, db: Session, user: AppUser, missing: bool, entered=None):
    rows = _rows(db, entered)
    unsaved = sum(1 for r in rows if r["saved"] is None)
    if missing:
        rows = [r for r in rows if r["saved"] is None or r["error"]]
    return render(request, "report_names.html", user, rows=rows, missing=missing, unsaved=unsaved)


@router.get("/report-names")
def list_report_names(
    request: Request,
    missing: bool = False,
    db: Session = Depends(get_db),
    user: AppUser = Depends(current_user),
):
    return _page(request, db, user, missing)


@router.post("/report-names")
async def save_report_names(
    request: Request,
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    """Save every row whose three names are filled; rows left fully empty are skipped.

    All-or-nothing: a row with only some names filled rejects the whole save, and the page comes
    back with every typed value kept and the bad rows marked.
    """
    form = await request.form()
    missing = form.get("missing") == "true"
    back = f"/report-names{'?missing=true' if missing else ''}"
    columns = [[str(v).strip() for v in form.getlist(name)] for name in FIELDS]
    if len({len(c) for c in columns}) != 1:
        flash(request, "Dữ liệu gửi lên không hợp lệ, hãy tải lại trang.", "error")
        return redirect(back)
    entered = {
        values[0]: dict(zip(FIELDS, values, strict=True), error="")
        for values in zip(*columns, strict=True)
    }
    known = set(db.scalars(select(SkuMapping.material_number).distinct()))
    saved = {r.material_number: r for r in db.scalars(select(ReportItemName))}
    filled = []
    for material, row in entered.items():
        values = [row[f] for f in VALUES]
        if material not in known:
            row["error"] = "Mã vật tư không có trong ánh xạ SAP"
        elif all(values):
            filled.append(row)
        elif any(values):
            row["error"] = "Cần đủ itemName, kích cỡ và variation"
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
    changed = 0
    for row in filled:
        record = saved.get(row["material_number"])
        if record is None:
            db.add(ReportItemName(**{f: row[f] for f in FIELDS}, updated_by=user.username))
        elif any(getattr(record, f) != row[f] for f in VALUES):
            for f in VALUES:
                setattr(record, f, row[f])
            record.updated_by = user.username
        else:
            continue
        changed += 1
    if changed:
        states.log_event(db, user.username, "report_names_saved", detail={"changed": changed})
    db.commit()
    flash(request, f"Đã lưu {changed} tên báo cáo ({len(filled) - changed} dòng không đổi).")
    return redirect(back)
