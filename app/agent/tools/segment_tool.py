"""`segment_tool` - `build(spec) -> SegmentTable`. Rule-based, khong LLM.
Xem docs/06-agent-design.md muc 6.4 va 6.6.

Day la NGUON DUY NHAT cho bang phan khuc: ca `/api/segments` (T06) va agent
(T08, khi playbook can chan dung phan khuc) deu goi ham `build_segment_table`
o day - khong con hai noi tinh rieng nhu ban dau T06.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from sqlalchemy import Engine, text

from app.analytics.clv import estimate_clv
from app.analytics.config import AnalyticsConfig, get_analytics_config
from app.analytics.segmentation import CustomerRow, compute_profit_p75, segment_all
from app.analytics.stats import wilson_ci
from app.data.engines import get_engine_ro

_CUSTOMER_QUERY = text(
    "SELECT customer_id, n_applications, n_disbursed, n_rejected, "
    "is_repeat_customer, is_never_applied, has_app, income_band, "
    "profit_to_date, worst_dayslate FROM mart.mart_customer_value"
)


def load_customers(engine: Engine | None = None) -> list[CustomerRow]:
    with (engine or get_engine_ro()).connect() as conn:
        rows = conn.execute(_CUSTOMER_QUERY).all()
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


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _dominant_behaviour_profile(members: list[CustomerRow]) -> tuple[str, bool]:
    """Ho so hanh vi (income_band, has_app) XUAT HIEN NHIEU NHAT trong phan
    khuc - dung de tra p_repeat cho CLV du bao cua CA phan khuc (mot phan
    khuc thuong khong dong nhat ve thu nhap/app, nen chon dai dien pho bien
    nhat, giong cach `validated.clv.by_segment` trong config/analytics.yaml
    da chon '12-20M|true' cho champion)."""
    counter = Counter((m.income_band, m.has_app) for m in members)
    (income_band, has_app), _ = counter.most_common(1)[0]
    return income_band, has_app


def build_segment_table(
    engine: Engine | None = None, cfg: AnalyticsConfig | None = None,
) -> list[dict[str, Any]]:
    """Phan khuc toan bo khach hang va tinh CLV du bao cho tung phan khuc.
    Tra ve danh sach dict, mot phan tu cho mot phan khuc, THEO DUNG THU TU
    luat trong config/analytics.yaml (high_risk truoc tien)."""
    cfg = cfg or get_analytics_config()
    customers = load_customers(engine)
    assignments, dist = segment_all(customers)

    members_by_segment: dict[str, list[CustomerRow]] = {}
    for c in customers:
        members_by_segment.setdefault(assignments[c.customer_id], []).append(c)

    out: list[dict[str, Any]] = []
    for rule in cfg.segment_rules:
        members = members_by_segment.get(rule.id, [])
        n = len(members)
        profits = [m.profit_to_date for m in members]
        n_repeat = sum(1 for m in members if m.is_repeat_customer)
        repeat_rate = n_repeat / n if n else 0.0
        repeat_ci = wilson_ci(n_repeat, n) if n else (0.0, 0.0)

        clv: dict[str, Any]
        if rule.id in cfg.not_applicable_segments or n == 0:
            clv = {"insufficient": True, "reason": "phan khuc chua giai ngan khoan nao"}
        else:
            income_band, has_app = _dominant_behaviour_profile(members)
            est = estimate_clv(
                n_customers=n, clv_to_date_mean=(sum(profits) / n if n else 0.0),
                income_band=income_band, has_app=has_app, cfg=cfg,
            )
            clv = asdict(est)

        out.append({
            "segment_id": rule.id,
            "label_vi": rule.label_vi,
            "action_hint_vi": rule.action_hint_vi,
            "n": n,
            "share": dist.share(rule.id),
            "avg_profit": (sum(profits) / n) if n else 0.0,
            "median_profit": _median(profits),
            "repeat_rate": repeat_rate,
            "repeat_rate_ci": list(repeat_ci),
            "income_band_distribution": dict(Counter(m.income_band for m in members)),
            "app_adoption": (sum(1 for m in members if m.has_app) / n) if n else 0.0,
            "clv_predicted": clv,
        })
    return out


def customers_in_segment(
    segment_id: str, engine: Engine | None = None,
) -> list[CustomerRow]:
    """Danh sach khach trong MOT phan khuc - dung cho export_tool (CSV)."""
    customers = load_customers(engine)
    assignments, _dist = segment_all(customers)
    return [c for c in customers if assignments.get(c.customer_id) == segment_id]


__all__ = [
    "build_segment_table", "customers_in_segment", "load_customers", "compute_profit_p75",
]
