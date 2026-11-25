"""Management reports: sales by month, channel, product, province and returns.

Every page reads the same Filters from the URL (so a link can be sent) and every page can be
downloaded as Excel with `?format=xlsx`, showing the same numbers. Read-only, for any signed-in
user.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from shoponline.clock import today_vn
from shoponline.db.models import AppUser, PlatformSetting, Shop
from shoponline.exports import report_workbook
from shoponline.reports import queries
from shoponline.reports.queries import Filters
from shoponline.web.app import current_user, get_db, render

router = APIRouter()
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DEFAULT_MONTHS = 12
MAX_ROWS_SHOWN = 500

# kind: text | num | money | percent
OVERVIEW_COLUMNS = (
    ("Tháng", "label", "text"),
    ("Giá trị trên sàn", "marketplace_value", "money"),
    ("Doanh thu hóa đơn", "invoice_value", "money"),
    ("Tiền thực nhận", "settled_value", "money"),
    ("Chênh giá/trợ giá", "subsidy_gap", "money"),
    ("Phí sàn", "platform_fee", "money"),
    ("Số đơn", "orders", "num"),
    ("Giá trị đơn trung bình", "average_order", "money"),
    ("Giá trị trả", "returned_value", "money"),
    ("Tỷ lệ trả", "return_rate", "percent"),
    ("Chờ hóa đơn", "missing_invoice", "num"),
    ("Chờ tiền về", "missing_settlement", "num"),
)
CHANNEL_COLUMNS = (
    ("Sàn", "platform", "text"),
    ("Shop", "shop_code", "text"),
    ("Division", "division", "text"),
    ("Số đơn", "orders", "num"),
    ("Số lượng", "quantity", "num"),
    ("Giá trị trên sàn", "marketplace_value", "money"),
)
PRODUCT_COLUMNS = (
    ("Tên hàng", "item_name", "text"),
    ("Quy cách", "size", "text"),
    ("Màu / loại", "variation", "text"),
    ("Số lượng", "quantity", "num"),
    ("Giá trị trên sàn", "marketplace_value", "money"),
)
PROVINCE_COLUMNS = (
    ("Tỉnh", "province", "text"),
    ("Số đơn", "orders", "num"),
    ("Số lượng", "quantity", "num"),
    ("Giá trị trên sàn", "marketplace_value", "money"),
)
RETURN_COLUMNS = (
    ("Tháng", "label", "text"),
    ("Lý do", "reason", "text"),
    ("Số phiếu", "documents", "num"),
    ("Giá trị trả", "returned_value", "money"),
)
REASONS = {"CANCEL": "Hủy đơn", "RETURN": "Trả hàng"}


def _month_label(period: date) -> str:
    return f"{period.month:02d}/{period.year}"


def _parse_month(text: str | None) -> date | None:
    try:
        year, month = (text or "").split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        return None


def _default_window() -> tuple[date, date]:
    today = today_vn()
    last = today.replace(day=1)
    index = last.year * 12 + last.month - 1 - (DEFAULT_MONTHS - 1)
    return date(index // 12, index % 12 + 1, 1), last


class Window:
    """The filters of one request: parsed, validated, and ready for both page and Excel."""

    def __init__(self, request: Request, db: Session):
        q = request.query_params
        default_from, default_to = _default_window()
        self.error = ""
        self.from_period = _parse_month(q.get("from")) or default_from
        self.to_period = _parse_month(q.get("to")) or default_to
        if self.from_period > self.to_period:
            self.error = "Tháng bắt đầu sau tháng kết thúc; hiển thị khoảng mặc định."
            self.from_period, self.to_period = default_from, default_to
        platforms = [p for p in q.getlist("platform") if p]
        shops = [s for s in q.getlist("shop") if s]
        known_platforms = set(db.scalars(select(PlatformSetting.platform)))
        known_shops = set(db.scalars(select(Shop.code)))
        self.platforms = tuple(p for p in platforms if p in known_platforms)
        self.shops = tuple(s for s in shops if s in known_shops)
        self.filters = Filters(self.from_period, self.to_period, self.platforms, self.shops)

    @property
    def query(self) -> str:
        pairs = [
            ("from", self.from_period.strftime("%Y-%m")),
            ("to", self.to_period.strftime("%Y-%m")),
            *(("platform", p) for p in self.platforms),
            *(("shop", s) for s in self.shops),
        ]
        return urlencode(pairs)

    def describe(self) -> str:
        parts = [f"Từ {_month_label(self.from_period)} đến {_month_label(self.to_period)}"]
        parts.append("sàn " + ", ".join(self.platforms) if self.platforms else "mọi sàn")
        parts.append("shop " + ", ".join(self.shops) if self.shops else "mọi shop")
        return "; ".join(parts)


def _cells(row: dict, columns) -> list:
    return [row.get(key) for _, key, _ in columns]


def _respond(request, db, user, template, title, file_stem, window, columns, rows, **context):
    notes = queries.data_notes(db, window.filters)
    if request.query_params.get("format") == "xlsx":
        headers = [h for h, _, _ in columns]
        workbook = report_workbook.build(
            title,
            window.describe(),
            notes,
            headers,
            [_cells(r, columns) for r in rows],
            money=[h for h, _, kind in columns if kind == "money"],
            percent=[h for h, _, kind in columns if kind == "percent"],
        )
        name = f"BAO CAO {file_stem} {window.from_period:%Y-%m} {window.to_period:%Y-%m}.xlsx"
        return Response(
            report_workbook.to_bytes(workbook),
            media_type=XLSX,
            headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"},
        )
    return render(
        request,
        template,
        user,
        title=title,
        window=window,
        columns=columns,
        rows=rows[:MAX_ROWS_SHOWN],
        truncated=max(0, len(rows) - MAX_ROWS_SHOWN),
        notes=notes,
        platforms=list(
            db.scalars(select(PlatformSetting.platform).order_by(PlatformSetting.platform))
        ),
        shops=list(db.scalars(select(Shop).order_by(Shop.platform, Shop.sort_order, Shop.code))),
        **context,
    )


@router.get("/reports")
def overview(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    window = Window(request, db)
    rows = [
        {**r, "label": _month_label(r["period"])}
        for r in queries.monthly_overview(db, window.filters)
    ]
    totals = _totals(rows)
    chart = {
        "labels": [r["label"] for r in rows],
        "marketplace": [r["marketplace_value"] for r in rows],
        "invoice": [r["invoice_value"] for r in rows],
        "settled": [r["settled_value"] for r in rows],
    }
    return _respond(
        request, db, user, "reports/overview.html", "Tổng quan bán hàng", "TONG QUAN", window,
        OVERVIEW_COLUMNS, rows, totals=totals, chart=chart,
    )  # fmt: skip


def _totals(rows: list[dict]) -> dict:
    def total(key):
        values = [r[key] for r in rows if r[key] is not None]
        return sum(values) if values else None

    orders = total("orders") or 0
    marketplace = total("marketplace_value") or 0
    invoice, returned = total("invoice_value"), total("returned_value")
    return {
        "marketplace_value": marketplace,
        "invoice_value": invoice,
        "settled_value": total("settled_value"),
        "platform_fee": total("platform_fee"),
        "orders": orders,
        "average_order": marketplace // orders if orders else None,
        "return_rate": (returned / invoice) if invoice and returned is not None else None,
    }


@router.get("/reports/channels")
def channels(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    window = Window(request, db)
    rows = queries.by_channel(db, window.filters)
    monthly = queries.monthly_by_channel(db, window.filters)
    labels = sorted({m["period"] for m in monthly})
    series = {}
    for m in monthly:
        series.setdefault(m["division"], {})[m["period"]] = m["marketplace_value"]
    chart = {
        "labels": [_month_label(p) for p in labels],
        "series": [
            {"name": name, "data": [by_month.get(p, 0) for p in labels]}
            for name, by_month in series.items()
        ],
    }
    return _respond(
        request, db, user, "reports/channels.html", "Theo sàn và shop", "SAN VA SHOP", window,
        CHANNEL_COLUMNS, rows, chart=chart,
    )  # fmt: skip


@router.get("/reports/products")
def products(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    window = Window(request, db)
    rows = queries.by_product(db, window.filters)
    names: dict[str, dict] = {}
    for row in rows:
        group = names.setdefault(
            row["item_name"] or "(không tên)", {"quantity": 0, "marketplace_value": 0, "rows": []}
        )
        group["quantity"] += row["quantity"]
        group["marketplace_value"] += row["marketplace_value"]
        group["rows"].append(row)
    groups = sorted(names.items(), key=lambda kv: -kv[1]["marketplace_value"])
    return _respond(
        request, db, user, "reports/products.html", "Theo sản phẩm", "SAN PHAM", window,
        PRODUCT_COLUMNS, rows, groups=groups[:MAX_ROWS_SHOWN],
    )  # fmt: skip


@router.get("/reports/provinces")
def provinces(
    request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)
):
    window = Window(request, db)
    rows = queries.by_province(db, window.filters)
    top = max((r["marketplace_value"] for r in rows), default=0)
    return _respond(
        request, db, user, "reports/provinces.html", "Theo tỉnh", "TINH", window,
        PROVINCE_COLUMNS, rows, top=top, unknown=queries.UNKNOWN_PROVINCE,
    )  # fmt: skip


@router.get("/reports/returns")
def returns(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    window = Window(request, db)
    rows = [
        {
            **r,
            "label": _month_label(r["period"]),
            "reason": REASONS.get(r["reason_kind"], r["reason_kind"]),
        }
        for r in queries.returns(db, window.filters)
    ]
    return _respond(
        request, db, user, "reports/returns.html", "Trả hàng", "TRA HANG", window,
        RETURN_COLUMNS, rows,
    )  # fmt: skip
