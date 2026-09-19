"""`/api/dashboard/*` - du lieu cho tab Chien dich (D1). KHONG GOI LLM: moi so
lieu tu SQL da kiem chung qua semantic layer (docs/09-api-ui.md muc 9.5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import get_metric_runner
from app.contracts import DateRange, Fact, Filter, MetricRequest
from app.data.repository import SqlMetricRunner

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Ky du lieu giao dich CO THAT DUY NHAT (DQ-03) - xem docs/02 muc 2.5.
_AUG_2026 = DateRange(start=dt.date(2026, 8, 1), end_exclusive=dt.date(2026, 9, 1))


def _fact_to_rows(fact: Fact) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != "_ref"} for row in fact.rows]


def _index_by(rows: list[dict[str, Any]], key: str) -> dict[Any, dict[str, Any]]:
    return {r[key]: r for r in rows}


@router.get("/campaigns")
def dashboard_campaigns(
    runner: SqlMetricRunner = Depends(get_metric_runner),
) -> list[dict[str, Any]]:
    """6 chien dich x cac chi so D1. Ghep hai truy van (dataset `application`
    va `campaign_daily`) vi compiler khong cho gop chi so tu hai dataset
    trong CUNG mot cau SELECT (bat bien 'khong bia ten', xem docs/05 muc 5.3)."""
    app_fact = runner.run(
        MetricRequest(
            metrics=(
                "applications", "disbursed_loans", "rejected_loans", "romi",
                "net_profit", "acquisition_spend", "approval_rate",
                "cost_per_disbursed", "profit_per_disbursed",
            ),
            dimensions=("campaign_id", "campaign_name", "channel"),
            date_range=_AUG_2026, order_by="net_profit", order_desc=True,
        ),
        fact_id="F1", title="Hieu qua theo chien dich",
    )
    lead_fact = runner.run(
        MetricRequest(
            metrics=("leads",), dimensions=("campaign_id",), date_range=_AUG_2026,
        ),
        fact_id="F2", title="Lead theo chien dich",
    )

    leads_by_campaign = _index_by(_fact_to_rows(lead_fact), "campaign_id")
    rows = _fact_to_rows(app_fact)
    for row in rows:
        lead_row = leads_by_campaign.get(row["campaign_id"], {})
        leads = lead_row.get("leads")
        row["leads"] = leads
        row["lead_to_application_rate"] = (
            row["applications"] / leads if leads else None
        )
    return rows


@router.get("/summary")
def dashboard_summary(
    runner: SqlMetricRunner = Depends(get_metric_runner),
) -> dict[str, Any]:
    """Thẻ KPI tổng. `median_profit_per_customer` va `negative_profit_share`
    LUON di kem `avg_profit_per_customer` (skew_guard trong config/analytics.yaml
    -> stats.skew_guard: |mean-median|/|mean| > 0,3 hoac ty le am > 30% thi
    bat buoc bao cao kem - o day luon bao cao ca ba, khong cho quy tac tu quyet)."""
    overall = runner.run(
        MetricRequest(metrics=("applications", "disbursed_loans", "net_profit", "romi"),
                      date_range=_AUG_2026),
        fact_id="F1", title="Tong quan chien dich",
    )
    customer_profit = runner.run(
        MetricRequest(
            metrics=("avg_profit_per_customer", "median_profit_per_customer",
                     "negative_profit_share", "repeat_customer_rate", "app_adoption_rate"),
            filters=(Filter(dimension="is_never_applied", op="eq", value=False),),
        ),
        fact_id="F2", title="Chan dung khach hang tong quan",
    )
    lead_total = runner.run(
        MetricRequest(metrics=("leads",), date_range=_AUG_2026),
        fact_id="F3", title="Tong lead",
    )

    row1 = overall.rows[0]
    row2 = customer_profit.rows[0]
    row3 = lead_total.rows[0]
    return {
        "applications": row1["applications"],
        "disbursed_loans": row1["disbursed_loans"],
        "net_profit": row1["net_profit"],
        "romi": row1["romi"],
        "leads": row3["leads"],
        "avg_profit_per_customer": row2["avg_profit_per_customer"],
        "median_profit_per_customer": row2["median_profit_per_customer"],
        "negative_profit_share": row2["negative_profit_share"],
        "repeat_customer_rate": row2["repeat_customer_rate"],
        "app_adoption_rate": row2["app_adoption_rate"],
    }


@router.get("/funnel")
def dashboard_funnel(
    runner: SqlMetricRunner = Depends(get_metric_runner),
) -> dict[str, Any]:
    """Xem docs/02-data-model.md muc 2.1: fact_lead khong co khoa noi toi
    fact_loan - day la TY LE TONG HOP muc toan chien dich."""
    from app.analytics.funnel import compute_funnel

    leads = runner.run(MetricRequest(metrics=("leads",), date_range=_AUG_2026),
                        "F1", "Tong lead")
    apps = runner.run(
        MetricRequest(metrics=("applications", "disbursed_loans"), date_range=_AUG_2026),
        "F2", "Tong ho so",
    )
    result = compute_funnel(
        leads=int(leads.rows[0]["leads"]),
        applications=int(apps.rows[0]["applications"]),
        disbursed=int(apps.rows[0]["disbursed_loans"]),
    )
    return {
        "stages": [{"name": s.name, "count": s.count} for s in result.stages],
        "steps": [
            {
                "from": s.from_stage, "to": s.to_stage, "from_count": s.from_count,
                "to_count": s.to_count, "rate": s.rate, "rate_ci": s.rate_ci,
            }
            for s in result.steps
        ],
        "caveat_vi": (
            "Tỷ lệ tổng hợp mức toàn chiến dịch, không phải attribution từng lead: "
            "bảng hồ sơ vay không có khóa nối về bảng lead (xem docs/02 mục 2.1)."
        ),
    }


@router.get("/trend")
def dashboard_trend(
    runner: SqlMetricRunner = Depends(get_metric_runner),
) -> list[dict[str, Any]]:
    """Xu huong 31 ngay (DQ-03: toan bo du lieu giao dich chi nam trong
    01/08-31/08/2026 - khong dung de suy dien theo mua vu/lien thang)."""
    fact = runner.run(
        MetricRequest(
            metrics=("applications", "disbursed_loans", "net_profit"),
            dimensions=("create_date",), date_range=_AUG_2026,
            order_by="create_date", order_desc=False, limit=31,
        ),
        fact_id="F1", title="Xu huong theo ngay",
    )
    return _fact_to_rows(fact)


__all__ = ["router"]
