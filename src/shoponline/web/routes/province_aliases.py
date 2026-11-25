"""Place names the reports cannot place in one of the 34 provinces, and where an admin puts them."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shoponline.db.models import AppUser, CustomerInfo, HistorySaleLine, ProvinceAlias
from shoponline.domain import states
from shoponline.domain.provinces import fold_key, last_part
from shoponline.domain.report_names import PROVINCES
from shoponline.web.app import current_user, flash, get_db, redirect, render, require_admin

router = APIRouter()
PAGE = "/province-aliases"
MAX_RAW = 100


def unresolved(db: Session) -> list[tuple[str, int]]:
    """(name as written, number of history lines and addresses) of every name with no alias,
    most frequent first. Names that differ only in case or tone marks count together."""
    known = set(db.scalars(select(ProvinceAlias.raw_key)))
    counts: Counter[str] = Counter()
    shown: dict[str, str] = {}
    history = db.execute(
        select(HistorySaleLine.city_raw, func.count())
        .where(HistorySaleLine.city_raw.is_not(None))
        .group_by(HistorySaleLine.city_raw)
    )
    addresses = Counter(
        last_part(address)
        for address in db.scalars(
            select(CustomerInfo.address).where(
                CustomerInfo.province.is_(None), CustomerInfo.address.is_not(None)
            )
        )
    )
    for name, count in (*history, *addresses.items()):
        key = fold_key(name)
        if not key or key in known:
            continue
        counts[key] += count
        shown.setdefault(key, name)
    return [(shown[key], count) for key, count in counts.most_common()]


@router.get(PAGE)
def list_aliases(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    return render(
        request,
        "province_aliases.html",
        user,
        pending=unresolved(db),
        provinces=sorted(PROVINCES),
        saved=list(
            db.scalars(
                select(ProvinceAlias)
                .where(ProvinceAlias.updated_by != "seed")
                .order_by(ProvinceAlias.updated_at.desc())
            )
        ),
    )


@router.post(PAGE)
def save_alias(
    request: Request,
    raw: str = Form(...),
    province: str = Form(...),
    db: Session = Depends(get_db),
    user: AppUser = Depends(require_admin),
):
    raw = raw.strip()
    key = fold_key(raw)
    if not key or len(key) > MAX_RAW:
        flash(request, "Tên chưa hợp lệ", "error")
    elif province not in PROVINCES:
        flash(request, "Chọn một trong 34 tỉnh", "error")
    else:
        alias = db.get(ProvinceAlias, key)
        if alias is None:
            db.add(ProvinceAlias(raw_key=key, province=province, updated_by=user.username))
        else:
            alias.province, alias.updated_by = province, user.username
        states.log_event(
            db, user.username, "province_alias_saved", detail={"raw": key, "province": province}
        )
        db.commit()
        flash(request, f"Đã quy '{raw}' về {province}.")
    return redirect(PAGE)
