"""`POST /api/chat` - hoi dap tu do qua SSE. Xem docs/15-streaming.md.

Ghi `ops.agent_trace` va lich Judge (L5) chay NGAM sau `done` la viec cua T11
(`app/telemetry/trace.py::save_and_run_judge`), noi qua tham so `on_finish`
cua `Orchestrator.answer_stream` - xem docstring cua tham so do de biet vi
sao Orchestrator khong tu giu TraceStore.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.agent.orchestrator import Orchestrator
from app.api.deps import get_orchestrator, get_trace_store
from app.api.schemas import ChatRequest
from app.contracts import AgentEvent, AgentState, TraceStore, Turn
from app.logging_ import get_logger
from app.telemetry.trace import save_and_run_judge

router = APIRouter(prefix="/api/chat", tags=["chat"])
log = get_logger(__name__)


def _json_default(obj: Any) -> Any:
    """Cot NUMERIC/DECIMAL cua Postgres tra ve `decimal.Decimal` (khong phai
    float), va Fact.rows co the mang UUID/date - `json.dumps` mac dinh khong
    biet cac kieu nay."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dt.date | dt.datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"khong serialize duoc kieu {type(obj).__name__}")


def _to_sse(ev: AgentEvent) -> dict[str, str]:
    return {
        "event": ev.event, "id": str(ev.seq),
        "data": json.dumps(ev.data, ensure_ascii=False, default=_json_default),
    }


async def _event_generator(
    request: Request, orchestrator: Orchestrator, trace_store: TraceStore, payload: ChatRequest,
) -> AsyncIterator[dict[str, str]]:
    history = [Turn(role=t.role, content=t.content) for t in payload.history]
    seq = 0

    async def on_finish(state: AgentState) -> AgentEvent | None:
        return await save_and_run_judge(
            state, trace_store, orchestrator.llm_client, orchestrator.prompts,
        )

    try:
        async for ev in orchestrator.answer_stream(
            payload.message, session_id=payload.session_id, history=history,
            on_finish=on_finish,
        ):
            if await request.is_disconnected():
                # Client da dong ket noi - dung phat su kien them, khong con
                # ai nhan; huy vong lap de giai phong task LLM/DB con lai.
                raise asyncio.CancelledError
            seq += 1
            yield _to_sse(AgentEvent(event=ev.event, data=ev.data, seq=seq))
    except asyncio.CancelledError:
        log.info("chat_stream_cancelled", message=payload.message[:80])
        raise


@router.post("")
async def chat(
    payload: ChatRequest, request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    trace_store: TraceStore = Depends(get_trace_store),
) -> EventSourceResponse:
    return EventSourceResponse(
        _event_generator(request, orchestrator, trace_store, payload),
        ping=15,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
