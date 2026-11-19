"""Server-side search and paging for history lists that can outgrow one page.

The page reads ``q`` (search words), ``page`` and ``size`` from the query string; other
query parameters (a status filter, a month) are kept in every link and form the pager draws.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

SIZES = (10, 25, 50, 100)
DEFAULT_SIZE = 25
OWN_PARAMS = ("q", "page", "size")


def _positive(value: str | None, default: int) -> int:
    try:
        number = int((value or "").strip())
    except ValueError:
        return default
    return number if number > 0 else default


@dataclass
class Page:
    items: list
    page: int
    size: int
    total: int
    q: str
    keep: list[tuple[str, str]] = field(default_factory=list)

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.size))

    @property
    def first(self) -> int:
        return (self.page - 1) * self.size + 1 if self.total else 0

    @property
    def last(self) -> int:
        return min(self.total, self.page * self.size)

    def url(self, page: int = 1, q: str | None = None) -> str:
        words = self.q if q is None else q
        params = list(self.keep)
        if words:
            params.append(("q", words))
        params.append(("size", str(self.size)))
        if page > 1:
            params.append(("page", str(page)))
        return "?" + urlencode(params)

    def numbers(self) -> list[int | None]:
        """Page numbers to draw (first, last, neighbours of the current page); None is a gap."""
        shown: list[int | None] = []
        last = 0
        for n in range(1, self.pages + 1):
            if n not in (1, self.pages) and abs(n - self.page) > 1:
                continue
            if last and n - last > 1:
                shown.append(None)
            shown.append(n)
            last = n
        return shown


def search_filter(q: str, *columns):
    """Every word must appear (case-insensitive) in at least one of the columns."""
    clauses = []
    for word in q.split():
        escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(or_(*(cast(c, String).ilike(f"%{escaped}%", escape="\\") for c in columns)))
    return and_(*clauses) if clauses else None


def search_words(request: Request) -> str:
    return " ".join(request.query_params.get("q", "").split())[:100]


def paginate(request: Request, db: Session, stmt, *search_columns) -> Page:
    """Apply the request's search words to ``stmt`` and return the requested page of it."""
    q = search_words(request)
    condition = search_filter(q, *search_columns) if search_columns else None
    if condition is not None:
        stmt = stmt.where(condition)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    size = _positive(request.query_params.get("size"), DEFAULT_SIZE)
    if size not in SIZES:
        size = DEFAULT_SIZE
    pages = max(1, -(-total // size))
    page = min(_positive(request.query_params.get("page"), 1), pages)
    items = list(db.scalars(stmt.limit(size).offset((page - 1) * size)))
    keep = [(k, v) for k, v in request.query_params.multi_items() if k not in OWN_PARAMS]
    return Page(items=items, page=page, size=size, total=total, q=q, keep=keep)
