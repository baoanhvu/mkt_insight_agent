"""Lap rap toan bo tool mot lan, dung chung cho ca phien. Xem
docs/06-agent-design.md muc 6.4. `sql_tool` (duong freeform co rao) duoc xay
day du o T12 - registry chua san cho slot do nhung de trong o day.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.tools.clv_tool import ClvTool
from app.agent.tools.export_tool import ExportTool
from app.agent.tools.metric_tool import MetricTool
from app.agent.tools.schema_tool import SchemaTool
from app.agent.tools.stats_tool import StatsTool
from app.analytics.config import AnalyticsConfig, get_analytics_config
from app.data.repository import SqlMetricRunner
from app.semantic.catalog import YamlCatalog, get_catalog


@dataclass(slots=True)
class ToolRegistry:
    metric_tool: MetricTool
    schema_tool: SchemaTool
    stats_tool: StatsTool
    clv_tool: ClvTool
    export_tool: ExportTool
    catalog: YamlCatalog
    analytics_cfg: AnalyticsConfig


def build_tool_registry(
    catalog: YamlCatalog | None = None,
    analytics_cfg: AnalyticsConfig | None = None,
    runner: SqlMetricRunner | None = None,
) -> ToolRegistry:
    catalog = catalog or get_catalog()
    analytics_cfg = analytics_cfg or get_analytics_config()
    runner = runner or SqlMetricRunner(catalog=catalog)

    return ToolRegistry(
        metric_tool=MetricTool(runner),
        schema_tool=SchemaTool(catalog),
        stats_tool=StatsTool(analytics_cfg),
        clv_tool=ClvTool(analytics_cfg),
        export_tool=ExportTool(),
        catalog=catalog,
        analytics_cfg=analytics_cfg,
    )


__all__ = ["ToolRegistry", "build_tool_registry"]
