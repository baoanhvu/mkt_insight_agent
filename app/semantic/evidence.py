"""Trien khai day du `EvidenceSet` (dia chi hoa bang chung cho Narrator).

`app/contracts.py` khai bao `EvidenceSet` la mot dataclass CU THE (khong phai
Protocol) nhung de than bon phuong thuc rong (`raise NotImplementedError`) -
day la cho co y de module nay dien vao, theo dung docs/17-implementation-guide.md
T03: "evidence.py hien thuc EvidenceSet.resolve/substitute/matches_any_cell/
all_string_values theo app/contracts.py".

Vi contracts.py la file protected (khong duoc viet lai), lop `EvidenceSet` o
day KE THUA lop trong contracts va CHI override bon phuong thuc - khong them
truong moi, nen khong xung dot voi `slots=True` cua lop cha. Toan bo phan con
lai cua ung dung PHAI dung lop nay (khong dung truc tiep contracts.EvidenceSet),
vi ban goc khong lam duoc gi ca.
"""

from __future__ import annotations

import re
from typing import Any

from app.contracts import Cell, ColumnSpec, Fact, NumericPolicy, Unit
from app.contracts import EvidenceSet as _BaseEvidenceSet
from app.web.formatting import format_value

# {{F1.r3.romi}}  hoac  {{D2}}  hoac  {{C1.diff}}
_REF_PATTERN = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")


def _find_fact(facts: list[Fact], fact_id: str) -> Fact | None:
    for f in facts:
        if f.fact_id == fact_id:
            return f
    return None


def _find_row(fact: Fact, row_ref: str) -> dict[str, Any] | None:
    """`row_ref` la "F1.r3" - tim theo khoa `_ref` gan san trong moi dong
    (docs/05 muc 5.4); neu dong khong co `_ref` (fact tu sinh thu cong trong
    test), rot ve dinh vi theo so thu tu 1-indexed "r<n>"."""
    for row in fact.rows:
        if row.get("_ref") == row_ref:
            return row
    m = re.fullmatch(r"r(\d+)", row_ref.rsplit(".", 1)[-1])
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(fact.rows):
            return fact.rows[idx]
    return None


def _column_spec(fact: Fact, column_name: str) -> ColumnSpec | None:
    for col in fact.columns:
        if col.name == column_name:
            return col
    return None


class EvidenceSet(_BaseEvidenceSet):
    """Ban trien khai THAT - dung lop nay o moi noi khac trong app/."""

    def resolve(self, ref: str) -> Cell | None:
        parts = ref.split(".")

        if len(parts) == 1:
            (only,) = parts
            for d in self.derived:
                if d.fact_id == only:
                    return Cell(
                        ref=ref, value=d.value, unit=d.unit, format="",
                        formatted=d.formatted,
                    )
            return None

        if len(parts) == 3 and parts[0].startswith("F"):
            fact_id, row_key, column_name = parts
            fact = _find_fact(self.facts, fact_id)
            if fact is None:
                return None
            row = _find_row(fact, f"{fact_id}.{row_key}")
            if row is None or column_name not in row:
                return None
            col_spec = _column_spec(fact, column_name)
            value = row[column_name]
            unit = col_spec.unit if col_spec else "text"
            fmt = col_spec.format if col_spec else ""
            return Cell(
                ref=ref, value=value, unit=unit, format=fmt,
                formatted=format_value(value, unit, fmt),
            )

        if len(parts) == 2 and parts[0].startswith("C"):
            comp_id, field = parts
            for idx, comp in enumerate(self.comparisons, start=1):
                if f"C{idx}" != comp_id:
                    continue
                if not hasattr(comp, field):
                    return None
                value = getattr(comp, field)
                comp_unit: Unit = "ratio" if isinstance(value, float) else "text"
                comp_fmt = "0.00" if comp_unit == "ratio" else ""
                return Cell(
                    ref=ref, value=value, unit=comp_unit, format=comp_fmt,
                    formatted=format_value(value, comp_unit, comp_fmt),
                )
            return None

        return None

    def substitute(self, text: str) -> tuple[str, list[str]]:
        unresolved: list[str] = []

        def _sub(m: re.Match[str]) -> str:
            ref = m.group(1)
            cell = self.resolve(ref)
            if cell is None:
                unresolved.append(ref)
                return m.group(0)  # giu nguyen "{{...}}" - de lop L2 chan ro rang
            return cell.formatted

        result = _REF_PATTERN.sub(_sub, text)
        return result, unresolved

    def matches_any_cell(self, value: float, policy: NumericPolicy) -> bool:
        for fact in self.facts:
            for row in fact.rows:
                if any(_numeric_match(value, v, policy) for v in row.values()):
                    return True
        return any(_numeric_match(value, d.value, policy) for d in self.derived)

    def all_string_values(self) -> set[str]:
        out: set[str] = set()
        for fact in self.facts:
            for row in fact.rows:
                for key, v in row.items():
                    if key == "_ref":
                        continue  # dia chi noi bo, khong phai gia tri nghiep vu
                    if isinstance(v, str):
                        out.add(v)
        return out


def _numeric_match(claimed: float, cell_value: Any, policy: NumericPolicy) -> bool:
    if not isinstance(cell_value, int | float):
        return False
    if isinstance(cell_value, bool):  # bool la subclass cua int - loai truoc
        return False
    cv = float(cell_value)

    if policy.mode == "exact":
        return claimed == cv
    if policy.mode == "round":
        return round(claimed, policy.decimals) == round(cv, policy.decimals)
    if policy.mode == "abs_tol":
        return abs(claimed - cv) <= policy.tol
    if policy.mode == "rel_tol":
        if cv == 0:
            return claimed == 0
        return abs(claimed - cv) / abs(cv) <= policy.tol
    return False


__all__ = ["EvidenceSet"]
