"""`/api/segments` - du lieu cho tab Chan dung KH (D2). KHONG GOI LLM.

Phan khuc duoc tinh bang `app/analytics/segmentation.py` (luat tuong minh,
xem docs/06-agent-design.md muc 6.6) tren du lieu THAT lay tu
`mart.mart_customer_value` - khong dung lai gia tri tinh san trong
config/analytics.yaml (nhung gia tri do la THAM CHIEU de doi chieu trong
test, khong phai nguon cho cau tra loi runtime).
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.analytics.clv import estimate_clv
from app.analytics.config import get_analytics_config
from app.analytics.segmentation import CustomerRow, compute_profit_p75, segment_all
from app.analytics.stats import wilson_ci
from app.data.engines import get_engine_ro

router = APIRouter(prefix="/api/segments", tags=["segments"])

_CUSTOMER_QUERY = text(
    "SELECT customer_id, n_applications, n_disbursed, n_rejected, "
    "is_repeat_customer, is_never_applied, has_app, income_band, "
    "profit_to_date, worst_dayslate FROM mart.mart_customer_value"
)


def _load_customers() -> list[CustomerRow]:
    with get_engine_ro().connect() as conn:
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


def build_segment_table() -> list[dict[str, Any]]:
    customers = _load_customers()
    assignments, dist = segment_all(customers)
    cfg = get_analytics_config()

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


@router.get("")
def list_segments() -> dict[str, Any]:
    segments = build_segment_table()
    total = sum(s["n"] for s in segments)
    return {
        "total_customers": total,
        "profit_p75_threshold": compute_profit_p75(_load_customers()),
        "segments": segments,
    }


@router.get("/{segment_id}/customers.csv")
def export_segment_customers_csv(segment_id: str) -> StreamingResponse:
    customers = _load_customers()
    assignments, _dist = segment_all(customers)
    members = [c for c in customers if assignments.get(c.customer_id) == segment_id]
    if not members and segment_id not in {s.id for s in get_analytics_config().segment_rules}:
        raise HTTPException(status_code=404, detail=f"phan khuc khong ton tai: '{segment_id}'")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["customer_id", "income_band", "has_app", "is_repeat_customer",
                      "profit_to_date"])
    for m in members:
        writer.writerow([m.customer_id, m.income_band, m.has_app, m.is_repeat_customer,
                          f"{m.profit_to_date:.0f}"])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="segment_{segment_id}.csv"'},
    )


__all__ = ["router", "build_segment_table"]
