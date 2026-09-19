"""Kiem tra app/analytics/segmentation.py doi chieu voi Postgres that va voi
`mart.v_customer_segment` (SQL view tuong duong, xem etl/sql/02_ddl_mart.sql).

BAT BUOC (docs/17-implementation-guide.md T05):
  tong = 2901, _unclassified = 0, high_risk = 97
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.analytics.config import get_analytics_config
from app.analytics.segmentation import (
    CustomerRow,
    classify_customer,
    compute_profit_p75,
    segment_all,
    segment_rule_order,
)
from app.settings import get_settings


def _skip_if_unreachable(engine: Engine) -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    engine = create_engine(get_settings().database.url)
    _skip_if_unreachable(engine)
    return engine


@pytest.fixture(scope="module")
def customers(pg_engine: Engine) -> list[CustomerRow]:
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT customer_id, n_applications, n_disbursed, n_rejected, "
                "is_repeat_customer, is_never_applied, has_app, income_band, "
                "profit_to_date, worst_dayslate FROM mart.mart_customer_value"
            )
        ).all()
    return [
        CustomerRow(
            customer_id=r.customer_id, n_applications=r.n_applications,
            n_disbursed=r.n_disbursed, n_rejected=r.n_rejected,
            is_repeat_customer=r.is_repeat_customer, is_never_applied=r.is_never_applied,
            has_app=r.has_app, income_band=r.income_band,
            profit_to_date=float(r.profit_to_date or 0), worst_dayslate=r.worst_dayslate,
        )
        for r in rows
    ]


EXPECTED_COUNTS = {
    "rejected_only": 1023, "dormant": 802, "never_activated": 347, "champion": 282,
    "app_gap": 159, "high_potential": 145, "high_risk": 97, "repeat_standard": 46,
}


def test_covers_all_customers_and_no_unclassified(customers: list[CustomerRow]) -> None:
    """BAT BUOC: tong = 2901, _unclassified = 0."""
    _assignments, dist = segment_all(customers)
    assert dist.total == 2901
    assert dist.unclassified == 0


def test_high_risk_count_matches_reference(customers: list[CustomerRow]) -> None:
    """BAT BUOC: high_risk = 97. Rui ro phai dung DAU danh sach luat de ghi de
    moi thuoc tinh khac - xem canh bao docs/06 muc 6.6 (ban dau chi bat 15/97
    vi dung o cuoi)."""
    _assignments, dist = segment_all(customers)
    assert dist.counts["high_risk"] == 97


@pytest.mark.parametrize("segment_id,expected_n", sorted(EXPECTED_COUNTS.items()))
def test_every_segment_count_matches_config_validated_table(
    customers: list[CustomerRow], segment_id: str, expected_n: int
) -> None:
    """Doi chieu toan bo 8 phan khuc voi config/analytics.yaml -> segmentation.validated."""
    _assignments, dist = segment_all(customers)
    assert dist.counts.get(segment_id, 0) == expected_n
    cfg_validated = get_analytics_config().raw["segmentation"]["validated"]["by_segment"]
    assert cfg_validated[segment_id]["n"] == expected_n


def test_segment_assignment_matches_sql_view(
    customers: list[CustomerRow], pg_engine: Engine
) -> None:
    """Logic Python (dung boi agent/analytics) va view SQL mart.v_customer_segment
    (dung boi dashboard/semantic layer) PHAI cho ra CUNG mot nhan cho tung khach -
    day la phep doi chieu cheo quan trong nhat cua file nay: neu hai noi troi
    nhau, mot ben da sai ma khong ai biet."""
    assignments, _dist = segment_all(customers)
    with pg_engine.connect() as conn:
        sql_rows = conn.execute(
            text("SELECT customer_id, segment FROM mart.v_customer_segment")
        ).all()

    mismatches = [
        (customer_id, assignments[customer_id], sql_segment)
        for customer_id, sql_segment in sql_rows
        if assignments[customer_id] != sql_segment
    ]
    assert mismatches == [], f"{len(mismatches)} khach lech nhan, vi du: {mismatches[:5]}"


def test_high_risk_rule_must_run_first(customers: list[CustomerRow]) -> None:
    """Khach vay lai nhieu lan (is_repeat_customer) nhung no qua han > 30 ngay
    PHAI la high_risk, khong duoc la champion - day chinh la loi da sua trong
    ADR-004."""
    risky_repeat_customers = [
        c for c in customers
        if c.is_repeat_customer and (c.worst_dayslate or 0) > 30
    ]
    assert len(risky_repeat_customers) > 0, "can it nhat mot ca thu de kiem tra"
    p75 = compute_profit_p75(customers)
    for c in risky_repeat_customers:
        assert classify_customer(c, p75) == "high_risk"


def test_segment_rule_order_matches_config() -> None:
    assert segment_rule_order() == (
        "high_risk", "champion", "repeat_standard", "high_potential",
        "app_gap", "dormant", "rejected_only", "never_activated",
    )


def test_compute_profit_p75_only_considers_applied_customers(
    customers: list[CustomerRow],
) -> None:
    p75 = compute_profit_p75(customers)
    never_applied_profit = {c.profit_to_date for c in customers if c.n_applications == 0}
    assert never_applied_profit == {0.0}  # 347 khach chua nop ho so, profit = 0
    assert p75 > 0  # neu tinh nham tren ca tap "chua nop ho so" (toan 0), p75 se ~0
