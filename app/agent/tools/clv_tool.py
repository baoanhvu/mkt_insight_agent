"""`clv_tool` - `estimate(segment) -> CLVEstimate`. Cong thuc minh bach
(docs/06-agent-design.md muc 6.4/6.5), boc mong quanh `app.analytics.clv`.
"""

from __future__ import annotations

from app.analytics.clv import estimate_clv
from app.analytics.config import AnalyticsConfig, get_analytics_config
from app.contracts import CLVEstimate


class ClvTool:
    def __init__(self, cfg: AnalyticsConfig | None = None) -> None:
        self.cfg = cfg or get_analytics_config()

    def estimate(
        self, *, n_customers: int, clv_to_date_mean: float, income_band: str, has_app: bool,
    ) -> CLVEstimate:
        return estimate_clv(
            n_customers=n_customers, clv_to_date_mean=clv_to_date_mean,
            income_band=income_band, has_app=has_app, cfg=self.cfg,
        )


__all__ = ["ClvTool"]
