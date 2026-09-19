"""`metric_tool` - duong CHINH (docs/06-agent-design.md muc 6.4). Da kiem
chung o T03/T04 (`app.semantic.compiler` + `app.data.repository`) - day chi
la lop boc mong cho dung ten trong bang cong cu.
"""

from __future__ import annotations

from app.contracts import Fact, MetricRequest
from app.data.repository import SqlMetricRunner


class MetricTool:
    """`run(MetricRequest) -> Fact`. 0 loi goi LLM."""

    def __init__(self, runner: SqlMetricRunner) -> None:
        self.runner = runner

    def run(
        self, req: MetricRequest, fact_id: str, title: str, *, dataset_override: str | None = None,
    ) -> Fact:
        return self.runner.run(req, fact_id, title, dataset_override=dataset_override)


__all__ = ["MetricTool"]
