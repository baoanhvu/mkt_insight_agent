"""Ghep noi Judge (L5) voi TraceStore: luu vet cau tra loi ngay lap tuc, roi
cham diem bang mo hinh SAU KHI cau tra loi da hien thi xong. Xem
docs/08-anti-hallucination.md muc 8.6 ("khong nam tren duong gang") va
docs/15-streaming.md muc 15.3 (su kien `judge` phat SAU `done` tren CUNG mot
ket noi SSE).
"""

from __future__ import annotations

from app.contracts import AgentEvent, AgentState, LLMClient, PromptStore, TraceStore
from app.logging_ import get_logger
from app.verify.judge import run_judge

log = get_logger(__name__)

# Judge chi co y nghia khi da co MOT cau tra loi thuc su de cham - cau bi tu
# choi/chan hoan toan (khong co evidence, hoac decision=BLOCKED) khong co gi
# de doi chieu, chay judge cho chung chi ton mot luot goi vo ich.
_SKIP_DECISIONS = frozenset({"BLOCKED", "CANCELLED"})


async def save_and_run_judge(
    state: AgentState, trace_store: TraceStore, llm_client: LLMClient, prompts: PromptStore,
) -> AgentEvent | None:
    """Ghi `state` vao TraceStore ngay (dong luon la ban ghi cuoi cung neu
    khong co judge). Neu du dieu kien, chay THEM mot luot goi LLM (Judge) va
    cap nhat lai dong do - goi ham nay SAU khi da phat xong su kien `done`,
    ket qua tra ve la mot `AgentEvent(event="judge")` de phat tiep, hoac None
    neu khong chay judge (cau bi tu choi/chan, hoac judge that bai)."""
    await trace_store.save(state)

    if (
        state.evidence is None
        or not state.narrative_final
        or state.decision.value in _SKIP_DECISIONS
    ):
        return None

    try:
        judge = await run_judge(state.narrative_final, state.evidence, llm_client, prompts)
    except Exception as exc:  # judge hong KHONG duoc lam sap tien trinh dang phuc vu
        log.warning("judge_failed", trace_id=str(state.trace_id), error=str(exc))
        return None

    await trace_store.update_judge(state.trace_id, judge)

    new_trust = state.trust.value if state.trust else 0.0
    if judge.contradiction_rate > 0.0:
        new_trust = 0.0
    return AgentEvent(event="judge", data={
        "entailment_rate": judge.entailment_rate,
        "contradiction_rate": judge.contradiction_rate,
        "neutral_rate": judge.neutral_rate,
        "trust": new_trust,
        "band": "BLOCKED" if judge.contradiction_rate > 0.0 else (state.trust.band.value if state.trust else None),
    })


__all__ = ["save_and_run_judge"]
