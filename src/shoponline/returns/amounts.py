"""Figures of a tax invoice and of a return, worked out from SAP data and the zrsd003 totals.

SAP gives each order line its value including VAT; the invoice shows value before VAT, so each
line's net is worked out from the zrsd003 totals and the rounding difference is pushed onto the
largest line. A kit is printed by Bkav as its parent line, so only main lines take part.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from shoponline.reconcile.so_link import is_main_line
from shoponline.returns.money import round_half_up


@dataclass(frozen=True)
class Blocked:
    """Why a figure cannot be worked out; each reason says what is wrong and how to clear it."""

    reasons: tuple[str, ...]
    # What can clear it: "missing_texts", "missing_money" or "numbering"; the page offers that fix.
    codes: frozenset[str] = frozenset()

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)


@dataclass(frozen=True)
class InvoiceLine:
    so_item_no: int
    material_number: str
    quantity: Decimal
    total_incl: int
    net: int
    unit_price: int


@dataclass(frozen=True)
class InvoiceLines:
    lines: tuple[InvoiceLine, ...]
    vat_rate: int
    net: int
    tax: int


def invoice_lines(items: Iterable, net: int, tax: int) -> InvoiceLines | Blocked:
    """items: SAP order lines (item_no, material_number, quantity, net_value_incl); net and tax
    are the zrsd003 invoice totals."""
    main = sorted((i for i in items if is_main_line(i.item_no)), key=lambda i: i.item_no)
    if not main:
        return Blocked(("SO không có dòng hàng chính; đọc lại zrsd001 của đơn này",))
    if net <= 0 or tax < 0:
        return Blocked((f"Tiền hóa đơn trong zrsd003 không hợp lệ (hàng {net}, thuế {tax})",))
    count = len(main)
    vat_rate = round_half_up(tax * 100, net)
    if abs(net * vat_rate - tax * 100) > count * 100:
        return Blocked((f"Thuế suất {tax * 100 / net:.2f}% không phải số phần trăm nguyên",))
    total = sum(i.net_value_incl for i in main)
    if total != net + tax:
        return Blocked(
            (
                f"Tổng giá trị các dòng SO {total:,} khác tổng hóa đơn {net + tax:,}: "
                "SO đã đổi sau khi xuất hóa đơn",
            )
        )
    nets = [round_half_up(i.net_value_incl * 100, 100 + vat_rate) for i in main]
    gap = net - sum(nets)
    if abs(gap) > count:
        return Blocked((f"Tiền hàng các dòng lệch tiền hàng hóa đơn {gap:,}, quá số dòng",))
    nets[nets.index(max(nets))] += gap
    lines = []
    for item, line_net in zip(main, nets, strict=True):
        quantity = Decimal(item.quantity)
        if quantity <= 0:
            return Blocked((f"Dòng SO {item.item_no} có số lượng {quantity}",))
        lines.append(
            InvoiceLine(
                so_item_no=item.item_no,
                material_number=item.material_number,
                quantity=quantity,
                total_incl=item.net_value_incl,
                net=line_net,
                # Display only: unit price times quantity may differ from the line amount.
                unit_price=round_half_up(line_net, quantity),
            )
        )
    return InvoiceLines(lines=tuple(lines), vat_rate=vat_rate, net=net, tax=tax)


@dataclass(frozen=True)
class ReturnedLine:
    so_item_no: int
    return_qty: Decimal
    amount: int


@dataclass(frozen=True)
class ReturnFigures:
    lines: tuple[ReturnedLine, ...]
    full_return: bool
    net: int
    tax: int


def returned(
    invoice: InvoiceLines, quantities: Mapping[int, Decimal | int]
) -> ReturnFigures | Blocked:
    """quantities: SO item number -> quantity returned (missing means none)."""
    known = {line.so_item_no for line in invoice.lines}
    unknown = sorted(set(quantities) - known)
    if unknown:
        return Blocked((f"Dòng {', '.join(map(str, unknown))} không có trên hóa đơn",))
    chosen: list[tuple[InvoiceLine, Decimal]] = []
    for line in invoice.lines:
        quantity = Decimal(quantities.get(line.so_item_no, 0))
        if quantity < 0 or quantity > line.quantity:
            return Blocked((f"Số trả của dòng {line.so_item_no} phải từ 0 đến {line.quantity}",))
        chosen.append((line, quantity))
    if not any(quantity > 0 for _, quantity in chosen):
        return Blocked(("Chọn ít nhất một dòng có số lượng trả lớn hơn 0",))
    full = all(quantity == line.quantity for line, quantity in chosen)
    if full:
        # The whole invoice: exactly the zrsd003 totals, whatever the line rounding.
        return ReturnFigures(
            lines=tuple(ReturnedLine(line.so_item_no, q, line.net) for line, q in chosen),
            full_return=True,
            net=invoice.net,
            tax=invoice.tax,
        )
    lines = tuple(
        ReturnedLine(line.so_item_no, quantity, round_half_up(line.net * quantity, line.quantity))
        for line, quantity in chosen
    )
    net = sum(line.amount for line in lines)
    return ReturnFigures(
        lines=lines,
        full_return=False,
        net=net,
        tax=round_half_up(net * invoice.vat_rate, 100),
    )
