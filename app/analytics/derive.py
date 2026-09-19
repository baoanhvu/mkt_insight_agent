"""Tinh khoi `derived` cua EvidenceSet - gia tri KHONG co san truc tiep tu SQL
(ty so, chenh lech giua hai fact) nhung LUON do CODE tinh, khong bao gio do
LLM (R1, CLAUDE.md). Xem docs/05-semantic-layer.md muc 5.4.

Bieu thuc (`expr`) do Planner khai bao dang chuoi, vi du "F1.r1.romi /
F1.r2.romi". No duoc phan tich bang module `ast` va CHI cho phep +, -, *, /,
so am, hang so, va tham chieu dang "F1.r1.ten_cot" - KHONG BAO GIO dung
`eval()` tren chuoi tuy y, vi day la du lieu do Planner (co the bi anh huong
boi cach dien dat cau hoi cua nguoi dung) sinh ra.
"""

from __future__ import annotations

import ast

from app.contracts import DerivedFact, Unit
from app.semantic.evidence import EvidenceSet
from app.web.formatting import format_value


class DerivedExprError(ValueError):
    """Bieu thuc khong hop le, hoac mot tham chieu trong do khong phan giai
    duoc ve mot Cell so thuc."""


def _dotted_name(node: ast.expr) -> str:
    parts: list[str] = []
    cur: ast.expr = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        raise DerivedExprError(f"tham chieu khong hop le trong bieu thuc derived: {ast.dump(node)}")
    return ".".join(reversed(parts))


def _eval(node: ast.expr, ev: EvidenceSet) -> float:
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, ev)
        right = _eval(node.right, ev)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise DerivedExprError("chia cho 0 trong bieu thuc derived")
            return left / right
        raise DerivedExprError(f"toan tu khong duoc ho tro: {ast.dump(node.op)}")

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, ev)

    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(
        node.value, bool
    ):
        return float(node.value)

    if isinstance(node, ast.Attribute | ast.Name):
        ref = _dotted_name(node)
        cell = ev.resolve(ref)
        if cell is None:
            raise DerivedExprError(f"khong phan giai duoc tham chieu: '{ref}'")
        if not isinstance(cell.value, int | float) or isinstance(cell.value, bool):
            raise DerivedExprError(f"tham chieu '{ref}' khong phai gia tri so: {cell.value!r}")
        return float(cell.value)

    raise DerivedExprError(
        f"cu phap khong duoc ho tro trong bieu thuc derived: {ast.dump(node)}"
    )


def compute_derived(
    expr: str,
    ev: EvidenceSet,
    *,
    fact_id: str,
    label_vi: str,
    unit: Unit = "ratio",
    format: str = "0.00",
) -> DerivedFact:
    """Tinh mot `DerivedFact` tu bieu thuc an toan tren cac Cell da co trong `ev`.

    Raises:
        DerivedExprError: bieu thuc khong parse duoc, dung cu phap khong duoc
            ho tro, hoac mot tham chieu khong phan giai duoc/khong phai so.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise DerivedExprError(f"bieu thuc khong parse duoc: '{expr}'") from exc

    value = _eval(tree.body, ev)
    return DerivedFact(
        fact_id=fact_id, expr=expr, value=value, label_vi=label_vi, unit=unit,
        formatted=format_value(value, unit, format),
    )


__all__ = ["compute_derived", "DerivedExprError"]
