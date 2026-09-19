"""Kiem tra app/verify/vi_text.py::parse_vi_number - ham DE VIET SAI NHAT
trong ca du an (xem docstring cua module do va CLAUDE.md). Tieng Viet dung
`.` cho hang nghin va `,` cho thap phan, NGUOC voi mac dinh tieng Anh - moi
ca duoi day deu doi chieu voi gia tri THAT ma mot nguoi doc tieng Viet se
hieu, khong phai gia tri Python se parse "tu nhien" neu doi mu sang tieng Anh.
"""

from __future__ import annotations

import pytest

from app.verify.vi_text import parse_vi_number

_UNIT_ALIASES = {
    "tỷ": 1_000_000_000.0, "ty": 1_000_000_000.0,
    "triệu": 1_000_000.0, "trieu": 1_000_000.0, "tr": 1_000_000.0,
    "nghìn": 1_000.0, "nghin": 1_000.0, "k": 1_000.0,
}

# (chuoi dau vao, gia tri ky vong) - None nghia la "khong phai so".
CASES: list[tuple[str, float | None]] = [
    # -- So nguyen co phan nghin (dau '.') --------------------------------
    ("392.498.500", 392498500.0),
    ("1.234.567", 1234567.0),
    ("2.687", 2687.0),
    ("1.625", 1625.0),
    ("1.062", 1062.0),
    ("14.530", 14530.0),
    ("2.901", 2901.0),
    ("-66.794.874", -66794874.0),
    ("100.000.000", 100000000.0),
    # -- So co ca phan nghin va phan thap phan (dau ',') ------------------
    ("392.498.500,25", 392498500.25),
    ("1.234,5", 1234.5),
    # -- So khong co phan nghin, co the co phan thap phan --------------------
    ("6,20", 6.2),
    ("1,60", 1.6),
    ("1,31", 1.31),
    ("0,67", 0.67),
    ("-0,41", -0.41),
    ("-1,85", -1.85),
    ("100", 100.0),
    ("0", 0.0),
    ("7", 7.0),
    # -- Phan tram - '%' chia 100 --------------------------------------------
    ("48,8%", 0.488),
    ("60,5%", 0.605),
    ("100%", 1.0),
    ("0%", 0.0),
    # -- Hau to don vi tieng Viet -> nhan he so ------------------------------
    ("1,2 tỷ", 1_200_000_000.0),
    ("1,2 ty", 1_200_000_000.0),
    ("392,5 triệu", 392_500_000.0),
    ("392,5 trieu", 392_500_000.0),
    ("392,5 tr", 392_500_000.0),
    ("15 nghìn", 15_000.0),
    ("15 nghin", 15_000.0),
    ("15 k", 15_000.0),
    # -- Hau to tien te khong doi he so ---------------------------------------
    ("392.498.500 VND", 392498500.0),
    ("392.498.500 đ", 392498500.0),
    ("392.498.500 d", 392498500.0),
    # -- Khoang trang / NBSP thua ---------------------------------------------
    (" 6,20 ", 6.2),
    ("2.687 ", 2687.0),
    # -- Fallback so kieu Anh lot vao (model hallucinate) ---------------------
    ("6.20", 6.2),
    ("0.67", 0.67),
    # -- CHUOI KHONG PHAI SO (ca nguoc - quan trong khong kem gi ca trung) ----
    ("CMP-FB-001", None),
    ("CMP-ZL-RL1", None),
    ("CUS-000123", None),
    ("APP-000456", None),
    ("", None),
    ("   ", None),
    (None, None),  # type: ignore[list-item]
    ("khong phai so", None),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_parse_vi_number(raw: str | None, expected: float | None) -> None:
    result = parse_vi_number(raw, _UNIT_ALIASES)  # type: ignore[arg-type]
    if expected is None:
        assert result is None, f"'{raw}' phai la None (khong phai so), nhung ra {result}"
    else:
        assert result is not None, f"'{raw}' phai parse duoc, nhung ra None"
        assert result == pytest.approx(expected), f"'{raw}' -> {result}, ky vong {expected}"


def test_at_least_30_cases_covered() -> None:
    """Yeu cau cua docs/17 T09: >= 30 ca cho parse_vi_number."""
    assert len(CASES) >= 30


def test_reverse_case_id_like_string_is_not_a_number() -> None:
    """Ca nguoc quan trong nhat: ma dinh danh dang CMP-FB-001 KHONG duoc coi
    la so, du chua chu so - nham lan nay se lam L2 chan sai mot cau tra loi
    dung."""
    assert parse_vi_number("CMP-FB-001") is None


def test_thousands_and_decimal_separators_are_opposite_of_english() -> None:
    """"1.234" (vi-VN) la so nguyen 1234, con "1,234" (vi-VN) la so thap phan
    1.234 - hai chuoi GIONG tieng Anh nhung nghia NGUOC HAN."""
    assert parse_vi_number("1.234") == pytest.approx(1234.0)
    assert parse_vi_number("1,234") == pytest.approx(1.234)
