"""Kiem tra DQ-01..09 va INV-1..7 tren ban sao DuckDB (khong can Postgres).

Dung fixture `mart_db` (tests/conftest.py) - mirror duoc dung TRUC TIEP tu
etl/sql/02_ddl_mart.sql, nen day la phep thu nhanh, chay o moi may, KHONG thay
the cho `python -m etl.dq_checks` chay tren Postgres thuc (script do con ghi
ket qua vao ops.dq_result va la cong kiem chan ETL o CI/prod).

Nguon dinh nghia gia tri: docs/02-data-model.md muc 2.5.
"""

from __future__ import annotations

from typing import Any


def _scalar(mart_db: Any, query: str) -> Any:
    row = mart_db.sql(query).fetchone()
    assert row is not None, f"truy van khong tra dong nao: {query}"
    return row[0]


# =============================================================================
# DQ-01..09 - profile du lieu da biet (WARN/INFO, chi doi chieu so lieu)
# =============================================================================

def test_dq01_disbursement_before_create(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM mart.mart_application WHERE dq_flag_date_order",
    )
    assert n == 6


def test_dq02_form_filling_time_nonpositive(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_digital_footprint WHERE form_filling_time <= 0",
    )
    assert n == 9


def test_dq03_single_month_span(mart_db: Any) -> None:
    n = _scalar(mart_db, "SELECT COUNT(DISTINCT CAST(create_at AS DATE)) FROM raw.fact_loan")
    assert n == 31


def test_dq05_fact_lead_customer_id_null(mart_db: Any) -> None:
    n = _scalar(mart_db, "SELECT COUNT(*) FROM raw.fact_lead WHERE customer_id IS NULL")
    assert n == 13116


def test_dq06_rejected_has_null_financials(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_loan WHERE loan_amount IS NULL AND tenure IS NULL",
    )
    assert n == 1062


def test_dq07_never_activated_customers(mart_db: Any) -> None:
    n = _scalar(
        mart_db, "SELECT COUNT(*) FROM mart.mart_customer_value WHERE is_never_applied"
    )
    assert n == 347


def test_dq09_balance_differs_from_amount(mart_db: Any) -> None:
    """Dinh nghia khop docs/02: NULL tinh la 'khac' (kieu pandas != trong
    profiling goc) - vi vay dung OR ro rang, KHONG dung IS DISTINCT FROM (coi
    NULL=NULL la khong khac, se thieu 1062 ho so tu choi)."""
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_loan "
        "WHERE loan_balance IS NULL OR loan_amount IS NULL OR loan_balance != loan_amount",
    )
    assert n == 1219


# =============================================================================
# INV-1..7 - bat bien cau truc THAT, muc BLOCK khi fail
# =============================================================================

def test_inv1_application_id_consistent_across_tables(mart_db: Any) -> None:
    diff_pnl = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_loan l "
        "FULL JOIN raw.loan_application_pnl p ON p.loan_application_id = l.application_id "
        "WHERE l.application_id IS NULL OR p.loan_application_id IS NULL",
    )
    diff_dfp = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_loan l "
        "FULL JOIN raw.fact_digital_footprint d ON d.loan_application_id = l.application_id "
        "WHERE l.application_id IS NULL OR d.loan_application_id IS NULL",
    )
    assert diff_pnl == 0
    assert diff_dfp == 0


def test_inv2_rejected_and_disbursed_are_exclusive(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM mart.mart_application WHERE is_rejected AND is_disbursed",
    )
    assert n == 0


def test_inv3_rejected_plus_disbursed_equals_total(mart_db: Any) -> None:
    rejected = _scalar(
        mart_db, "SELECT COUNT(*) FROM mart.mart_application WHERE is_rejected"
    )
    disbursed = _scalar(
        mart_db, "SELECT COUNT(*) FROM mart.mart_application WHERE is_disbursed"
    )
    total = _scalar(mart_db, "SELECT COUNT(*) FROM mart.mart_application")
    assert rejected == 1062
    assert disbursed == 1625
    assert rejected + disbursed == total == 2687


def test_inv4_every_loan_customer_exists_in_dim_customer(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_loan l "
        "LEFT JOIN raw.dim_customer c ON c.customer_id = l.customer_id "
        "WHERE c.customer_id IS NULL",
    )
    assert n == 0


def test_inv5_every_loan_subchannel_exists_in_dim_campaign(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM raw.fact_loan l "
        "LEFT JOIN mart.dim_campaign c ON c.sub_channel = l.sub_channel "
        "WHERE c.sub_channel IS NULL",
    )
    assert n == 0


def test_inv6_rejected_applications_have_zero_revenue(mart_db: Any) -> None:
    n = _scalar(
        mart_db,
        "SELECT COUNT(*) FROM mart.mart_application WHERE is_rejected AND total_revenue != 0",
    )
    assert n == 0


def test_inv7_mart_application_rowcount_matches_fact_loan(mart_db: Any) -> None:
    mart_n = _scalar(mart_db, "SELECT COUNT(*) FROM mart.mart_application")
    raw_n = _scalar(mart_db, "SELECT COUNT(*) FROM raw.fact_loan")
    assert mart_n == raw_n == 2687
