"""`POST /invocations` - cong KHONG streaming cho Zalo/API ngoai. Xem
docs/15-streaming.md muc 15.9 va docs/12-build-deploy.md muc 12.7 (checklist
nghiem thu deploy doi hoi endpoint nay tra ve `answer_markdown` + `evidence`
+ `trust`).

Dung CHUNG mot `Orchestrator.answer()` voi `/api/chat` - khong co duong
nghiep vu thu hai (docs/15 muc 15.9).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends

from app.agent.orchestrator import Orchestrator
from app.api.deps import get_orchestrator, get_trace_store
from app.api.schemas import ChatRequest
from app.contracts import TraceStore, Turn

router = APIRouter(tags=["invocations"])


@router.post("/invocations")
async def invoke(
    payload: ChatRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    trace_store: TraceStore = Depends(get_trace_store),
) -> dict[str, Any]:
    history = [Turn(role=t.role, content=t.content) for t in payload.history]
    t0 = time.monotonic()
    state = await orchestrator.answer(
        payload.message, session_id=payload.session_id, history=history,
    )
    await trace_store.save(state)

    return {
        "trace_id": str(state.trace_id),
        "answer_markdown": state.narrative_final,
        "trust": (
            {"score": state.trust.value, "band": state.trust.band.value}
            if state.trust else None
        ),
        "evidence": [
            {"fact_id": f.fact_id, "title": f.title, "row_count": f.row_count}
            for f in (state.evidence.facts if state.evidence else [])
        ],
        "meta": {
            "llm_calls": state.llm_calls,
            "latency_ms": int((time.monotonic() - t0) * 1000),
        },
    }


__all__ = ["router"]
