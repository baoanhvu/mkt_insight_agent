"""Kiem tra app/analytics/stats.py - ham thuan, khong can DB cho phan lon test.
Ba ca doi chieu voi Postgres that (danh dau ro) dung de xac nhan cong thuc
tai lap dung cac gia tri da cong bo trong config/analytics.yaml.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.analytics.stats import (
    anova_oneway,
    bootstrap_mean_diff,
    cohens_d,
    two_proportion_ztest,
    wilson_ci,
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


# =============================================================================
# wilson_ci - ham thuan
# =============================================================================

def test_wilson_ci_matches_required_reference_value() -> None:
    """BAT BUOC (docs/17-implementation-guide.md T05): wilson_ci(103, 284) ~ (0.309, 0.420)."""
    lo, hi = wilson_ci(103, 284)
    assert lo == pytest.approx(0.309, abs=1e-3)
    assert hi == pytest.approx(0.420, abs=1e-3)


@pytest.mark.parametrize(
    "x,n,expected_lo,expected_hi",
    [
        (103, 284, 0.309, 0.420),   # 12-20M|true
        (51, 221, 0.180, 0.291),    # 12-20M|false
        (68, 348, 0.157, 0.240),    # 8-12M|true
        (39, 256, 0.113, 0.201),    # 8-12M|false
        (329, 1507, 0.198, 0.240),  # global
    ],
)
def test_wilson_ci_matches_all_p_repeat_lookup_cells(
    x: int, n: int, expected_lo: float, expected_hi: float
) -> None:
    """Doi chieu voi tung o trong config/analytics.yaml -> clv.p_repeat_lookup."""
    lo, hi = wilson_ci(x, n)
    assert lo == pytest.approx(expected_lo, abs=2e-3)
    assert hi == pytest.approx(expected_hi, abs=2e-3)


def test_wilson_ci_narrower_than_wald_for_small_n() -> None:
    """Voi n nho va p gan bien, Wilson phai KHONG bao gio vuot [0, 1] - Wald
    co the tra am hoac > 1."""
    lo, hi = wilson_ci(16, 17)  # p = 0.941, giong nhom ">=20M|true" (n=17)
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_ci_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        wilson_ci(5, 0)
    with pytest.raises(ValueError):
        wilson_ci(-1, 10)
    with pytest.raises(ValueError):
        wilson_ci(11, 10)


# =============================================================================
# two_proportion_ztest / cohens_d / bootstrap_mean_diff - ham thuan
# =============================================================================

def test_two_proportion_ztest_significant_case() -> None:
    """12-20M+app (36,3%, n=284) vs <8M+app (15,7%, n=216) - chenh lech lon,
    ca hai mau deu du lon."""
    res = two_proportion_ztest(103, 284, 34, 216)
    assert res.diff == pytest.approx(103 / 284 - 34 / 216, abs=1e-9)
    assert res.significant is True
    assert res.p_value < 0.05


def test_two_proportion_ztest_not_significant_when_sample_too_small() -> None:
    res = two_proportion_ztest(16, 17, 5, 7)  # ca hai duoi nguong 30
    assert res.significant is False


def test_cohens_d_zero_for_identical_groups() -> None:
    assert cohens_d([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(0.0)


def test_bootstrap_mean_diff_is_deterministic_with_fixed_seed() -> None:
    a = [100.0, 250.0, -50.0, 400.0, 180.0, 90.0, 300.0, -120.0]
    b = [50.0, 30.0, -100.0, 20.0, 10.0, 90.0, -40.0, 60.0]
    r1 = bootstrap_mean_diff(a, b, seed=42)
    r2 = bootstrap_mean_diff(a, b, seed=42)
    assert r1.p_value == r2.p_value
    assert r1.ci == r2.ci


def test_bootstrap_mean_diff_requires_nonempty_groups() -> None:
    with pytest.raises(ValueError):
        bootstrap_mean_diff([], [1.0])


# =============================================================================
# anova_oneway - BAT BUOC doi chieu voi Postgres that
# =============================================================================

def test_anova_occupation_matches_reference(pg_engine: Engine) -> None:
    """BAT BUOC: ANOVA 7 nhom nghe -> p = 0,9718, significant = False.

    Nghe nghiep KHONG duoc dung lam truc phan khuc (docs/06 muc 6.6) - day la
    bang chung thong ke cho quyet dinh do."""
    with pg_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT occupation, profit_to_date FROM mart.mart_customer_value "
                "WHERE n_applications > 0"
            )
        ).all()

    groups_by_occupation: dict[str, list[float]] = {}
    for occupation, profit in rows:
        groups_by_occupation.setdefault(occupation, []).append(float(profit))

    assert len(groups_by_occupation) == 7, sorted(groups_by_occupation)
    result = anova_oneway(list(groups_by_occupation.values()))

    assert result.p_value == pytest.approx(0.9718, abs=2e-3)
    assert result.significant is False


def test_freelancer_vs_grab_driver_profit_difference_matches_reference(
    pg_engine: Engine,
) -> None:
    """config/analytics.yaml: freelancer_vs_grab_p: 0.5246, cohens_d: 0.0480."""
    with pg_engine.connect() as conn:
        freelancer = [
            float(r[0]) for r in conn.execute(
                text(
                    "SELECT profit_to_date FROM mart.mart_customer_value "
                    "WHERE n_applications > 0 AND occupation = 'Freelancer'"
                )
            ).all()
        ]
        grab = [
            float(r[0]) for r in conn.execute(
                text(
                    "SELECT profit_to_date FROM mart.mart_customer_value "
                    "WHERE n_applications > 0 AND occupation = 'Lai xe cong nghe'"
                )
            ).all()
        ]

    result = bootstrap_mean_diff(freelancer, grab)
    d = cohens_d(freelancer, grab)
    assert result.p_value == pytest.approx(0.5246, abs=0.05)
    assert d == pytest.approx(0.0480, abs=0.01)
