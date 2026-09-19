"""Kiem tra app/analytics/clv.py. Cong thuc: docs/06-agent-design.md muc 6.5."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.analytics.clv import estimate_clv, lookup_p_repeat
from app.analytics.config import get_analytics_config
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


def test_estimate_clv_insufficient_below_min_sample() -> None:
    """BAT BUOC (docs/17-implementation-guide.md T05): estimate_clv(n=29) -> insufficient=True."""
    est = estimate_clv(
        n_customers=29, clv_to_date_mean=100_000.0, income_band=">=20M", has_app=True,
    )
    assert est.insufficient is True
    assert est.point is None and est.lower is None and est.upper is None


def test_estimate_clv_sufficient_above_min_sample() -> None:
    est = estimate_clv(
        n_customers=30, clv_to_date_mean=100_000.0, income_band="12-20M", has_app=True,
    )
    assert est.insufficient is False
    assert est.point is not None
    assert est.lower is not None and est.upper is not None
    assert est.lower <= est.point <= est.upper


def test_lookup_p_repeat_uses_detailed_cell_when_sample_large_enough() -> None:
    cfg = get_analytics_config()
    cell, source = lookup_p_repeat("12-20M", True, cfg)
    assert source == "12-20M|true"
    assert cell.n == 284
    assert cell.x == 103


def test_lookup_p_repeat_falls_back_through_income_to_global_for_small_cells() -> None:
    """Nhom '>=20M': o chi tiet n=17 (co app)/n=7 (khong app), gop theo thu
    nhap van chi n=24 - ca hai duoi 30 nen rot xuong gia tri toan tap (docs/06
    muc 6.5, doan canh bao ve p_repeat)."""
    cfg = get_analytics_config()
    cell, source = lookup_p_repeat(">=20M", True, cfg)
    assert source == "global"
    assert cell.n == 1507


def test_estimate_clv_assumptions_always_present_and_mention_horizon_factor() -> None:
    est = estimate_clv(
        n_customers=100, clv_to_date_mean=0.0, income_band="12-20M", has_app=True,
    )
    assert len(est.assumptions) >= 3
    assert any("horizon_factor" in a for a in est.assumptions)
    assert any("31 ngay" in a for a in est.assumptions)


def test_estimate_clv_matches_champion_segment_reference(pg_engine: Engine) -> None:
    """config/analytics.yaml: validated.clv.by_segment.champion = point 1716873,
    lower 1673474, upper 1763233, p_repeat_source '12-20M|true'."""
    from app.analytics.segmentation import CustomerRow, segment_all

    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT customer_id, n_applications, n_disbursed, n_rejected, "
                "is_repeat_customer, is_never_applied, has_app, income_band, "
                "profit_to_date, worst_dayslate FROM mart.mart_customer_value"
            )
        ).all()

    customers = [
        CustomerRow(
            customer_id=r.customer_id, n_applications=r.n_applications,
            n_disbursed=r.n_disbursed, n_rejected=r.n_rejected,
            is_repeat_customer=r.is_repeat_customer, is_never_applied=r.is_never_applied,
            has_app=r.has_app, income_band=r.income_band,
            profit_to_date=float(r.profit_to_date or 0), worst_dayslate=r.worst_dayslate,
        )
        for r in rows
    ]
    assignments, _dist = segment_all(customers)
    champion_ids = {cid for cid, seg in assignments.items() if seg == "champion"}
    assert len(champion_ids) == 282

    champion_profit = [c.profit_to_date for c in customers if c.customer_id in champion_ids]
    mean_profit = sum(champion_profit) / len(champion_profit)

    est = estimate_clv(
        n_customers=len(champion_ids), clv_to_date_mean=mean_profit,
        income_band="12-20M", has_app=True,
    )
    assert est.insufficient is False
    assert est.p_repeat_source == "12-20M|true"
    assert est.point == pytest.approx(1_716_873, rel=0.02)
    assert est.lower == pytest.approx(1_673_474, rel=0.02)
    assert est.upper == pytest.approx(1_763_233, rel=0.02)
