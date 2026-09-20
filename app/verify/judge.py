"""L5 - LLM judge (docs/08-anti-hallucination.md muc 8.6). Chay BAT DONG BO,
KHONG nam tren duong gang tra loi: Orchestrator/telemetry (T11) goi ham nay
SAU khi cau tra loi da qua L0-L4 va da tra ve nguoi dung, ket qua cap nhat
sau qua `TraceStore.update_judge()` + su kien SSE "judge".

CHU Y R3: module nay dung `LLMClient`/`PromptStore` CHI la kieu (Protocol)
tu app.contracts, nhan instance da duoc goi tu ben ngoai truyen vao - khong
tu import app.llm/app.data/app.api. Cung KHONG import app.agent (dung lai
mot ban rut gon cua serialize_evidence ngay trong file nay) de tranh verify/
phu thuoc nguoc vao agent/.
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.contracts import CheckResult, EvidenceSet, JudgeResult, LLMClient, PromptStore, Severity


def _serialize_evidence_for_judge(ev: EvidenceSet) -> str:
    lines: list[str] = []
    for fact in ev.facts:
        lines.append(f"# {fact.fact_id}: {fact.title} (n={fact.row_count})")
        for row in fact.rows:
            ref = row.get("_ref", fact.fact_id)
            parts = [f"{ref}.{k} = {v!r}" for k, v in row.items() if k != "_ref"]
            lines.append("   " + "   ".join(parts))
    for i, comp in enumerate(ev.comparisons, start=1):
        lines.append(
            f"# C{i}: so sanh {comp.left} vs {comp.right} ({comp.metric}) - "
            f"diff={comp.diff!r}, p_value={comp.p_value!r}, significant={comp.significant}"
        )
    return "\n".join(lines)


def _parse_judge_json(
    text: str, *, model: str, prompt_version: str, latency_ms: int,
) -> JudgeResult:
    """Parse loi hoac thieu truong bat buoc -> JudgeResult AN TOAN (nghieng
    ve HEDGE: entailment_rate=0, neutral_rate=1) - mot judge tra loi hong
    KHONG duoc ngam dinh la 'khong co van de gi' (se lam BLOCKED/HEDGE bi bo
    sot that su co bug o judge, khong phai o cau tra loi)."""
    try:
        data: dict[str, Any] = json.loads(text)
        return JudgeResult(
            entailment_rate=float(data["entailment_rate"]),
            neutral_rate=float(data["neutral_rate"]),
            contradiction_rate=float(data["contradiction_rate"]),
            grounding_score=float(data.get("grounding_score", data["entailment_rate"])),
            claims=list(data.get("claims") or []),
            model=model, prompt_version=prompt_version, latency_ms=latency_ms,
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JudgeResult(
            entailment_rate=0.0, neutral_rate=1.0, contradiction_rate=0.0,
            grounding_score=0.0, claims=[],
            model=model, prompt_version=prompt_version, latency_ms=latency_ms,
        )


async def run_judge(
    answer: str, ev: EvidenceSet, llm_client: LLMClient, prompts: PromptStore,
) -> JudgeResult:
    """Mot loi goi LLM DUY NHAT, temperature=0 (config/verify.yaml judge.temperature)."""
    rendered = prompts.render("judge_grounding")
    messages = [*rendered.messages, {
        "role": "user",
        "content": f"EVIDENCE:\n{_serialize_evidence_for_judge(ev)}\n\nSTATEMENT:\n{answer}",
    }]
    t0 = time.monotonic()
    text = await llm_client.complete(
        messages, temperature=rendered.params.get("temperature", 0.0),
        max_tokens=rendered.params.get("max_tokens", 400), response_format="json",
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    return _parse_judge_json(
        text, model=getattr(llm_client, "model", ""),
        prompt_version=rendered.version, latency_ms=latency_ms,
    )


def judge_to_check_result(judge: JudgeResult) -> CheckResult:
    """Quy doi JudgeResult (ba nhan) thanh CheckResult de hoa chung vao
    `app.verify.pipeline.compute_trust` cung cach voi L2/L3/L4 (docs/08 muc
    8.6-8.7): `contradiction_rate > 0` -> hard-fail (BLOCK), nguoc lai diem
    la `grounding_score` voi trong so 'judge' trong config/verify.yaml."""
    passed = judge.contradiction_rate == 0.0
    return CheckResult(
        name="judge", passed=passed, score=judge.grounding_score,
        severity=Severity.BLOCK,
        details={
            "entailment_rate": judge.entailment_rate, "neutral_rate": judge.neutral_rate,
            "contradiction_rate": judge.contradiction_rate, "claims": judge.claims,
            "model": judge.model, "prompt_version": judge.prompt_version,
            "latency_ms": judge.latency_ms,
        },
        message_vi=None if passed else (
            "Mô hình kiểm tra lại phát hiện phát biểu mâu thuẫn với dữ liệu nguồn."
        ),
    )


__all__ = ["run_judge", "judge_to_check_result"]
