"""`PgTraceStore` - trien khai `app.contracts.TraceStore` tren Postgres, ghi
qua role `mkt_trace_rw` (chi INSERT/SELECT/UPDATE vao schema `ops`, xem
app/data/engines.py::get_engine_trace). Xem docs/08-anti-hallucination.md
muc 8.8 va etl/sql/03_ddl_ops.sql (DDL, protected - nguon su that cho ten cot).

R2: khong bao gio noi chuoi du lieu nguoi dung vao SQL - moi gia tri di qua
bind parameter (`:ten_bien`), ke ca khi gia tri la JSON (ep kieu bang
`CAST(:x AS JSONB)` ngay trong van ban SQL tinh, khong phai ghep chuoi).
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from app.contracts import AgentState, CheckResult, EvidenceSet, JudgeResult
from app.data.engines import get_engine_trace
from app.settings import get_settings


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dt.date | dt.datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"khong serialize duoc kieu {type(obj).__name__}")


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def _evidence_to_dict(ev: EvidenceSet | None) -> dict[str, Any] | None:
    """Ghi TOM TAT (khong ghi toan bo rows - co the lon va lap lai o
    answer_md/checks) - du de tra cuu "cau hoi nay dung fact nao"."""
    if ev is None:
        return None
    return {
        "evidence_id": ev.evidence_id, "data_version": ev.data_version,
        "facts": [
            {"fact_id": f.fact_id, "title": f.title, "row_count": f.row_count}
            for f in ev.facts
        ],
        "caveats": ev.caveats, "assumptions": ev.assumptions,
    }


def _checks_to_dict(checks: list[CheckResult]) -> dict[str, Any]:
    return {
        c.name: {
            "passed": c.passed, "score": c.score, "severity": c.severity.value,
            "details": c.details, "message_vi": c.message_vi,
        }
        for c in checks
    }


class PgTraceStore:
    """Trien khai `app.contracts.TraceStore`."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine_trace()

    async def save(self, state: AgentState) -> None:
        settings = get_settings()
        latency_ms = None
        if state.started_at is not None:
            latency_ms = int(
                (dt.datetime.now(dt.UTC) - state.started_at).total_seconds() * 1000
            )

        params = {
            "trace_id": str(state.trace_id),
            "session_id": state.session_id,
            "question": state.question,
            "question_norm": state.question.strip().lower(),
            "intent": state.intent.value if state.intent else None,
            "playbook": state.playbook,
            "route_confidence": state.route_confidence,
            "evidence": _dumps(_evidence_to_dict(state.evidence)),
            "answer_md": state.narrative_final,
            "checks": _dumps(_checks_to_dict(state.checks)),
            "trust_score": state.trust.value if state.trust else None,
            "decision": state.decision.value,
            "block_reason": state.block_reason,
            "prompt_version": state.prompt_version or "",
            "model_name": str(settings.llm.get("model", "")),
            "profile": settings.profile,
            "metrics_version": state.metrics_version,
            "data_version": state.evidence.data_version if state.evidence else None,
            "latency_ms": latency_ms,
            "llm_calls": state.llm_calls,
            "tokens_in": state.tokens_in,
            "tokens_out": state.tokens_out,
        }
        with self._engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ops.agent_trace (
                    trace_id, session_id, question, question_norm, intent, playbook,
                    route_confidence, evidence, answer_md, checks, trust_score, decision,
                    block_reason, prompt_version, model_name, profile, metrics_version,
                    data_version, latency_ms, llm_calls, tokens_in, tokens_out
                ) VALUES (
                    :trace_id, :session_id, :question, :question_norm, :intent, :playbook,
                    :route_confidence, CAST(:evidence AS JSONB), :answer_md,
                    CAST(:checks AS JSONB), :trust_score, :decision, :block_reason,
                    :prompt_version, :model_name, :profile, :metrics_version,
                    :data_version, :latency_ms, :llm_calls, :tokens_in, :tokens_out
                )
                ON CONFLICT (trace_id) DO UPDATE SET
                    answer_md = EXCLUDED.answer_md, checks = EXCLUDED.checks,
                    trust_score = EXCLUDED.trust_score, decision = EXCLUDED.decision,
                    latency_ms = EXCLUDED.latency_ms
            """), params)

    async def update_judge(self, trace_id: UUID, judge: JudgeResult) -> None:
        judge_dict = {
            "judge": {
                "entailment_rate": judge.entailment_rate, "neutral_rate": judge.neutral_rate,
                "contradiction_rate": judge.contradiction_rate,
                "grounding_score": judge.grounding_score, "claims": judge.claims,
                "model": judge.model, "prompt_version": judge.prompt_version,
                "latency_ms": judge.latency_ms,
            },
        }
        with self._engine.begin() as conn:
            conn.execute(text("""
                UPDATE ops.agent_trace
                SET checks = COALESCE(checks, '{}'::jsonb) || CAST(:judge AS JSONB)
                WHERE trace_id = :trace_id
            """), {"trace_id": str(trace_id), "judge": _dumps(judge_dict)})

    async def get(self, trace_id: UUID) -> dict[str, Any] | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM ops.agent_trace WHERE trace_id = :trace_id"),
                {"trace_id": str(trace_id)},
            ).mappings().first()
        return dict(row) if row is not None else None


__all__ = ["PgTraceStore"]
