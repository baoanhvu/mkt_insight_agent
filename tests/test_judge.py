"""Kiem tra app/verify/judge.py (L5) va viec noi Judge + TraceStore qua
`app/telemetry/trace.py::save_and_run_judge`. Xem docs/17 T11.

BAT BUOC (docs/17 T11): judge tra ve SAU su kien `done`, cap nhat
`ops.agent_trace`; ba cot prompt_version/model_name/profile KHONG duoc NULL.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.agent.orchestrator import Orchestrator, build_orchestrator
from app.contracts import AgentEvent, AgentState, ColumnSpec, Fact, JudgeResult, Severity
from app.prompts.loader import PromptLoader
from app.semantic.evidence import EvidenceSet
from app.settings import get_settings
from app.telemetry.store import PgTraceStore
from app.telemetry.trace import save_and_run_judge
from app.verify.judge import judge_to_check_result, run_judge


class FakeJudgeLLM:
    """Tra ve MOT chuoi co dinh cho moi loi goi complete() - du de kiem tra
    parse dung/sai, khong can that su goi mang."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        return self.response

    async def stream(self, messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield self.response


@pytest.fixture
def evidence() -> EvidenceSet:
    fact = Fact(
        fact_id="F1", title="ROMI theo chien dich", query_id="q1", sql="SELECT ...",
        columns=[ColumnSpec(name="romi", label="ROMI", unit="ratio", format="0.00")],
        rows=[{"_ref": "F1.r1", "romi": 6.201503}],
        row_count=1,
    )
    return EvidenceSet(
        evidence_id="ev1", generated_at=dt.datetime.now(), data_version="etl_run_1", facts=[fact],
    )


@pytest.fixture
def prompts() -> PromptLoader:
    return PromptLoader()


async def test_run_judge_parses_supported_response(
    evidence: EvidenceSet, prompts: PromptLoader,
) -> None:
    response = (
        '{"claims":[{"text":"ROMI 6,20","label":"SUPPORTED","evidence_ref":"F1.r1.romi"}],'
        '"entailment_rate":1.0,"neutral_rate":0.0,"contradiction_rate":0.0,"grounding_score":1.0}'
    )
    llm = FakeJudgeLLM(response)
    result = await run_judge("ROMI đạt 6,20.", evidence, llm, prompts)

    assert result.entailment_rate == 1.0
    assert result.contradiction_rate == 0.0
    assert len(llm.calls) == 1
    # Hoi quy: loader.py phai giu ca 'statement' trong few-shot LAN CA trong
    # tin nhan that (khong chi con 'evidence') - xem sua trong app/prompts/loader.py.
    assert any("STATEMENT:" in m["content"] for m in llm.calls[0])


async def test_run_judge_parses_contradiction_response(
    evidence: EvidenceSet, prompts: PromptLoader,
) -> None:
    response = (
        '{"claims":[],"entailment_rate":0.0,"neutral_rate":0.0,'
        '"contradiction_rate":1.0,"grounding_score":0.0}'
    )
    llm = FakeJudgeLLM(response)
    result = await run_judge("Tỷ lệ duyệt đạt 72%.", evidence, llm, prompts)

    assert result.contradiction_rate == 1.0
    check = judge_to_check_result(result)
    assert not check.passed
    assert check.severity == Severity.BLOCK


async def test_run_judge_malformed_json_defaults_to_safe_hedge(
    evidence: EvidenceSet, prompts: PromptLoader,
) -> None:
    """LLM tra ve chuoi khong phai JSON (hoac thieu truong) -> KHONG duoc
    ngam dinh la 'khong co van de gi' (PASS diem tuyet doi) - phai nghieng
    ve phia can trong (diem 0, khong hard-fail)."""
    llm = FakeJudgeLLM("day khong phai JSON hop le")
    result = await run_judge("ROMI đạt 6,20.", evidence, llm, prompts)

    assert result.entailment_rate == 0.0
    assert result.neutral_rate == 1.0
    check = judge_to_check_result(result)
    assert check.passed  # contradiction_rate = 0 nen khong hard-fail...
    assert check.score == 0.0  # ...nhung diem = 0, keo trust xuong qua trong so 'judge'


def test_judge_to_check_result_fully_supported_passes() -> None:
    judge = JudgeResult(
        entailment_rate=1.0, neutral_rate=0.0, contradiction_rate=0.0, grounding_score=1.0,
    )
    check = judge_to_check_result(judge)
    assert check.name == "judge"
    assert check.passed
    assert check.score == 1.0


def _skip_if_unreachable() -> None:
    try:
        engine = create_engine(get_settings().database.url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


@pytest.fixture
def orchestrator() -> Orchestrator:
    _skip_if_unreachable()
    return build_orchestrator()


async def test_judge_event_follows_done_and_updates_agent_trace(orchestrator: Orchestrator) -> None:
    """BAT BUOC (docs/17 T11): judge tra ve SAU `done`, cap nhat ops.agent_trace;
    prompt_version/model_name/profile khong duoc NULL."""
    fake = FakeJudgeLLM(
        "{{F4.r1.campaign_name}} lỗ với ROMI {{F4.r1.romi}}.",
    )
    orchestrator.llm_client = fake  # type: ignore[assignment]
    orchestrator.narrator.llm_client = fake  # type: ignore[assignment]
    trace_store = PgTraceStore()

    async def on_finish(state: AgentState) -> AgentEvent | None:
        return await save_and_run_judge(
            state, trace_store, orchestrator.llm_client, orchestrator.prompts,
        )

    events = [
        ev async for ev in orchestrator.answer_stream(
            "Chiến dịch nào đang lỗ?", on_finish=on_finish,
        )
    ]

    names = [ev.event for ev in events]
    assert "done" in names
    assert "judge" in names
    assert names.index("judge") > names.index("done")

    done_event = next(ev for ev in events if ev.event == "done")
    trace_id = done_event.data["trace_id"]

    engine = create_engine(get_settings().database.url)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT prompt_version, model_name, profile FROM ops.agent_trace "
                "WHERE trace_id = :tid"
            ),
            {"tid": trace_id},
        ).mappings().first()

    assert row is not None, "ops.agent_trace phai co dong cho trace_id nay"
    assert row["prompt_version"] not in (None, "")
    assert row["model_name"] not in (None, "")
    assert row["profile"] not in (None, "")
