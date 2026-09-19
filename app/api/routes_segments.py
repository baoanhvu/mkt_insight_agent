"""`/api/segments` - du lieu cho tab Chan dung KH (D2). KHONG GOI LLM.

Logic thuc su nam trong `app.agent.tools.segment_tool` - route o day CHI goi
tool do va boc thanh JSON/CSV, giong cach agent (T08) se dung CUNG mot tool
khi playbook can chan dung phan khuc (mot nguon su that duy nhat).
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.tools.segment_tool import (
    build_segment_table,
    compute_profit_p75,
    customers_in_segment,
    load_customers,
)
from app.analytics.config import get_analytics_config

router = APIRouter(prefix="/api/segments", tags=["segments"])


@router.get("")
def list_segments() -> dict[str, Any]:
    segments = build_segment_table()
    total = sum(s["n"] for s in segments)
    return {
        "total_customers": total,
        "profit_p75_threshold": compute_profit_p75(load_customers()),
        "segments": segments,
    }


@router.get("/{segment_id}/customers.csv")
def export_segment_customers_csv(segment_id: str) -> StreamingResponse:
    members = customers_in_segment(segment_id)
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


__all__ = ["router"]
