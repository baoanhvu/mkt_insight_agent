"""Pydantic DTO cho request/response. Xem docs/09-api-ui.md muc 9.1.

Cac endpoint dashboard tra ve `list[dict]`/`dict` truc tiep (khong boc Pydantic
model rieng cho tung bang chi so) vi hinh dang cot thay doi theo `MetricRequest`
- danh cho Pydantic o day cho hai viec on dinh, quan trong nhat: health/ready
(hop dong voi AgentBase Runtime) va tra loi loi thong nhat.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "error"]
    dq: Literal["ok", "blocked", "unknown"]
    catalog: Literal["ok", "error"]
    detail: str | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: str = ""
    retryable: bool = False


class VersionResponse(BaseModel):
    app: str
    profile: str
    metrics_version: str


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[ChatTurn] = []


class ActionRow(BaseModel):
    id: str
    label_vi: str
    target_segment: str | None
    target_metric: str
    effort: str
    priority: int
    requires_experiment: bool
    impact_caveat_vi: str
    eligible: bool
    eligibility_note_vi: str
    impact_vnd: float | None = None
    validated: dict[str, Any] | None = None


__all__ = [
    "HealthResponse", "ReadyResponse", "ErrorResponse", "VersionResponse", "ActionRow",
    "ChatTurn", "ChatRequest",
]
