"""Kiem tra app/web/formatting.py. Xem docs/09-api-ui.md muc 9.8.

`None` LUON hien "—" (em dash), khong bao gio "0" - nham hai thu nay
khien "khong co du lieu" trong nhu "khong co doanh thu", mot loi nghiem trong
trong bao cao tai chinh.
"""

from __future__ import annotations

import pytest

from app.web.formatting import fmt_count, fmt_pct, fmt_ratio, fmt_vnd, fmt_vnd_short, format_value


def test_fmt_vnd_matches_claude_md_pinned_example() -> None:
    """BAT BUOC (docs/17-implementation-guide.md T06):
    fmt_vnd(392498488) == "392.498.488 VND"."""
    assert fmt_vnd(392_498_488) == "392.498.488 VND"


@pytest.mark.parametrize(
    "value,expected",
    [
        (392_498_488, "392.498.488 VND"),
        (-66_794_874, "-66.794.874 VND"),
        (0, "0 VND"),
        (None, "—"),
    ],
)
def test_fmt_vnd(value: float | None, expected: str) -> None:
    assert fmt_vnd(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (392_498_488, "392,5 tr"),
        (1_600_000_000, "1,6 tỷ"),
        (-66_794_874, "-66,8 tr"),
        (5_000, "5.000 VND"),
        (None, "—"),
    ],
)
def test_fmt_vnd_short(value: float | None, expected: str) -> None:
    assert fmt_vnd_short(value) == expected


@pytest.mark.parametrize(
    "value,d,expected",
    [
        (0.604764, 1, "60,5%"),
        (0.604764, 0, "60%"),
        (-0.406315, 1, "-40,6%"),
        (None, 1, "—"),
    ],
)
def test_fmt_pct(value: float | None, d: int, expected: str) -> None:
    assert fmt_pct(value, d) == expected


@pytest.mark.parametrize(
    "value,d,expected",
    [
        (6.201503, 2, "6,20"),
        (-1.846089, 2, "-1,85"),
        (1.601062, 2, "1,60"),
        (None, 2, "—"),
    ],
)
def test_fmt_ratio_matches_claude_md_pinned_romi_table(
    value: float | None, d: int, expected: str
) -> None:
    """BAT BUOC: sau khi lam tron o format "0.00", 6 gia tri ROMI trong
    CLAUDE.md phai hien thi dung nhu vay."""
    assert fmt_ratio(value, d) == expected


def test_fmt_count() -> None:
    assert fmt_count(2687) == "2.687"
    assert fmt_count(None) == "—"


def test_none_never_renders_as_zero() -> None:
    """Nham 'khong co du lieu' thanh '0' la loi nghiem trong trong bao cao
    tai chinh - kiem tra ro tren ca bon ham chinh."""
    for fn in (fmt_vnd, fmt_vnd_short, fmt_ratio, fmt_count):
        assert fn(None) != "0"
        assert "—" in fn(None)
    assert fmt_pct(None) != "0%"


class TestFormatValueDispatcher:
    def test_vnd_unit(self) -> None:
        assert format_value(392_498_488, "vnd", "#,##0") == "392.498.488 VND"

    def test_ratio_unit_plain(self) -> None:
        assert format_value(6.201503, "ratio", "0.00") == "6,20"

    def test_ratio_unit_percent_format(self) -> None:
        assert format_value(0.604764, "ratio", "0.0%") == "60,5%"

    def test_percent_unit(self) -> None:
        assert format_value(0.538, "percent", "0.0%") == "53,8%"

    def test_count_unit(self) -> None:
        assert format_value(2687, "count", "#,##0") == "2.687"

    def test_text_unit_passthrough(self) -> None:
        assert format_value("CMP-ZL-RL1", "text", "") == "CMP-ZL-RL1"

    def test_none_always_dash_regardless_of_unit(self) -> None:
        for unit in ("vnd", "ratio", "percent", "count", "text", "years"):
            assert format_value(None, unit, "") == "—"

    def test_years_unit_with_decimals(self) -> None:
        assert format_value(36.2, "years", "0.0") == "36,2"
