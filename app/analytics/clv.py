"""Uoc luong CLV du bao. Cong thuc: docs/06-agent-design.md muc 6.5.

    clv_predicted = clv_to_date + p_repeat(ho so hanh vi) * avg_profit_per_repeat_loan * horizon_factor

`p_repeat` LAY TU BANG TRA (income_band x has_app), TUYET DOI KHONG lay tu ty
le vay lai TRONG chinh phan khuc gia tri dang uoc luong - phan khuc `champion`
duoc DINH NGHIA bang is_repeat_customer=true nen ty le do trong no luon la 1.0,
mot vong lap logic da duoc phat hien va sua (xem canh bao trong docs/06 muc 6.5
va ADR-004). Day la ly do duy nhat ham nay nhan `income_band`/`has_app` cua
PHAN KHUC dang xet, khong nhan chinh ty le vay lai cua phan khuc do.

Kieu tra ve la `app.contracts.CLVEstimate` (hop dong chung, xem CLVEstimator
Protocol trong contracts.py) - KHONG dinh nghia lop rieng cung ten o day, vi
lam vay se tao hai kieu "CLVEstimate" khac nhau trong cung du an.
"""

from __future__ import annotations

from app.analytics.config import AnalyticsConfig, PRepeatCell, get_analytics_config
from app.analytics.stats import wilson_ci
from app.contracts import CLVEstimate


def lookup_p_repeat(
    income_band: str, has_app: bool, cfg: AnalyticsConfig,
) -> tuple[PRepeatCell, str]:
    """Chuoi du phong khi o chi tiet co n < nguong toi thieu:
    (income_band, has_app) -> income_band -> toan tap.

    Vi du nhom '>=20M': o chi tiet co n=17 (co app) / n=7 (khong app), gop
    theo thu nhap van chi n=24 - ca hai deu duoi 30 nen rot xuong `global`."""
    key = f"{income_band}|{'true' if has_app else 'false'}"
    detailed = cfg.p_repeat_by_income_and_app.get(key)
    if detailed is not None and detailed.usable and detailed.n >= cfg.clv_min_sample_size:
        return detailed, key

    by_income = cfg.p_repeat_by_income.get(income_band)
    if by_income is not None and by_income.usable and by_income.n >= cfg.clv_min_sample_size:
        return by_income, income_band

    return cfg.p_repeat_global, "global"


def estimate_clv(
    *,
    n_customers: int,
    clv_to_date_mean: float,
    income_band: str,
    has_app: bool,
    cfg: AnalyticsConfig | None = None,
) -> CLVEstimate:
    """Uoc luong CLV du bao cho MOT nhom khach (thuong la mot phan khuc).

    Args:
        n_customers: co mau CUA NHOM dang uoc luong (khac co mau cua o trong
            bang tra p_repeat) - duoi `cfg.clv_min_sample_size` (mac dinh 30)
            se tra `insufficient=True` va `point/lower/upper` deu None.
        clv_to_date_mean: trung binh `profit_to_date` cua nhom (CLV da thuc hien).
        income_band, has_app: ho so hanh vi dung de tra p_repeat - KHONG phai
            ty le vay lai cua nhom, xem docstring module.
    """
    cfg = cfg or get_analytics_config()

    if n_customers < cfg.clv_min_sample_size:
        return CLVEstimate(
            point=None, lower=None, upper=None, insufficient=True,
            reason=f"n = {n_customers} < {cfg.clv_min_sample_size} - khong du mau de uoc luong",
        )

    cell, source = lookup_p_repeat(income_band, has_app, cfg)
    lo, hi = wilson_ci(cell.x, cell.n, conf=0.95)
    p_repeat = cell.x / cell.n
    nxt = cfg.avg_profit_per_repeat_loan
    h = cfg.horizon_factor

    assumptions = [
        f"horizon_factor = {h} (gia dinh cau hinh, khong suy ra tu du lieu - "
        "xem config/analytics.yaml -> clv.horizon_factor_note_vi)",
        f"p_repeat = {p_repeat:.1%}, CI95 Wilson = [{lo:.1%}, {hi:.1%}], "
        f"nguon = ho so hanh vi '{source}' (n={cell.n})",
        f"loi nhuan trung binh moi khoan tai vay = {nxt:,.0f} VND",
        "du lieu giao dich chi co 31 ngay (DQ-03): khong ngoai suy theo mua vu",
    ]

    return CLVEstimate(
        point=clv_to_date_mean + p_repeat * nxt * h,
        lower=clv_to_date_mean + lo * nxt * h,
        upper=clv_to_date_mean + hi * nxt * h,
        insufficient=False,
        assumptions=assumptions,
        p_repeat_source=source,
    )


__all__ = ["estimate_clv", "lookup_p_repeat"]
