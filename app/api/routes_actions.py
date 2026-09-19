"""`/api/actions` - danh sach khuyen nghi D3 (docs/06-agent-design.md muc 6.7).
KHONG GOI LLM. Logic thuc su nam trong `app.agent.tools.action_tool` - agent
(T08) dung CUNG mot tool khi playbook co section `source: actions`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.agent.tools.action_tool import list_actions_with_eligibility
from app.api.deps import get_metric_runner
from app.data.repository import SqlMetricRunner

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("")
def list_actions(
    runner: SqlMetricRunner = Depends(get_metric_runner),
) -> list[dict[str, Any]]:
    return list_actions_with_eligibility(runner)


__all__ = ["router"]
