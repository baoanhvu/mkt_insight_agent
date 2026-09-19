"""`export_tool` - `to_csv(segment) -> bytes`. Danh sach `customer_id` cho
CRM (docs/06-agent-design.md muc 6.4). Dung lai `segment_tool.customers_in_segment`.
"""

from __future__ import annotations

import csv
import io

from app.agent.tools.segment_tool import customers_in_segment


class ExportTool:
    def to_csv(self, segment_id: str) -> bytes:
        members = customers_in_segment(segment_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["customer_id", "income_band", "has_app", "is_repeat_customer", "profit_to_date"]
        )
        for m in members:
            writer.writerow(
                [m.customer_id, m.income_band, m.has_app, m.is_repeat_customer,
                 f"{m.profit_to_date:.0f}"]
            )
        return buf.getvalue().encode("utf-8")


__all__ = ["ExportTool"]
