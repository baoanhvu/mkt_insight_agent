"""Dinh dang so theo quy uoc vi-VN: phan nghin dung `.`, phan thap phan dung `,`.

NGUON DUY NHAT cho quy tac nay - dung boi ca `app/semantic/evidence.py` (sinh
`Cell.formatted`) va boi cac route API/UI (T06). Frontend phai dung cung logic
qua `Intl.NumberFormat('vi-VN')` va co test doi chieu hai ben tren cung bo gia
tri, de khong troi lech - vi lop kiem chung numeric grounding (08 muc 8.3) so
khop CHINH chuoi nay, khong phai gia tri so goc.

`None` LUON hien "—" (em dash), khong bao gio la "0" - nham hai thu nay khien
"khong co du lieu" trong nhu "khong co doanh thu", mot loi nghiem trong trong
bao cao tai chinh. Xem docs/09-api-ui.md muc 9.8.
"""

from __future__ import annotations

from typing import Any

_NO_DATA = "—"


def fmt_vnd(v: float | None) -> str:
    """392498500 -> "392.498.500 VND"."""
    if v is None:
        return _NO_DATA
    return f"{v:,.0f}".replace(",", ".") + " VND"


def fmt_vnd_short(v: float | None) -> str:
    """Rut gon cho truc bieu do: 392498500 -> "392,5 tr"; 1_600_000_000 -> "1,6 tỷ"."""
    if v is None:
        return _NO_DATA
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:,.1f}".replace(",", ".").replace(".", ",", 1) + " tỷ"
    if a >= 1e6:
        return f"{v / 1e6:,.1f}".replace(".", ",") + " tr"
    return fmt_vnd(v)


def fmt_pct(v: float | None, d: int = 1) -> str:
    """0.604764 -> "60,5%" (d=1)."""
    return _NO_DATA if v is None else f"{v * 100:.{d}f}".replace(".", ",") + "%"


def fmt_ratio(v: float | None, d: int = 2) -> str:
    """6.201503 -> "6,20" (d=2)."""
    return _NO_DATA if v is None else f"{v:.{d}f}".replace(".", ",")


def fmt_count(v: float | None) -> str:
    """2687 -> "2.687". Dung cho unit=count - giong fmt_vnd nhung KHONG co hau to."""
    if v is None:
        return _NO_DATA
    return f"{v:,.0f}".replace(",", ".")


def _decimals_in_format(fmt: str) -> int:
    """"#,##0" -> 0. "0.0%" -> 1. "0.00" -> 2."""
    if "." not in fmt:
        return 0
    frac = fmt.split(".", 1)[1]
    return len(frac.rstrip("%"))


def format_value(value: Any, unit: str, fmt: str = "") -> str:
    """Dieu phoi theo `unit` (tu Metric/ColumnSpec) va `format` (chuoi kieu Excel
    trong metrics.yml, vi du "#,##0", "0.0%", "0.00"). Day la ham `Cell.formatted`
    va cac cot hien thi trong bang du lieu deu di qua.

    `None` -> "—" bat ke unit. Chuoi/bool giu nguyen (unit "text")."""
    if value is None:
        return _NO_DATA
    if unit == "text" or isinstance(value, bool):
        # bool: khong tu dinh dang "Co/Khong" o day (R5 - chuoi hien thi tieng
        # Viet phai nam trong YAML). Lop goi (web/template) tu tra nhan qua
        # cau hinh dimension. O day chi tra chuoi ky thuat lam du lieu goc.
        return str(value)

    decimals = _decimals_in_format(fmt)
    is_percent_fmt = fmt.strip().endswith("%")

    if unit == "vnd":
        return fmt_vnd(float(value))
    if unit == "percent" or (unit == "ratio" and is_percent_fmt):
        return fmt_pct(float(value), d=decimals or 1)
    if unit == "ratio":
        return fmt_ratio(float(value), d=decimals or 2)
    if unit == "count":
        return fmt_count(float(value))
    if unit in ("days", "months", "years", "seconds", "rate_pct_month"):
        return fmt_ratio(float(value), d=decimals) if decimals else fmt_count(float(value))
    return fmt_ratio(float(value), d=decimals or 2)


__all__ = [
    "fmt_vnd", "fmt_vnd_short", "fmt_pct", "fmt_ratio", "fmt_count", "format_value",
]
