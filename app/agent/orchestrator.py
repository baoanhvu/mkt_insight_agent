"""Dieu phoi may trang thai INTAKE..RENDER. Trien khai `app.contracts.Orchestrator`.
Xem docs/06-agent-design.md muc 6.1.

Ghi TRACE day du vao `ops.agent_trace` la viec cua T11 (`app/telemetry/`) -
AgentState o day duoc dien day nhung CHUA tu ghi xuong DB; T11 chi can them
mot loi goi `TraceStore.save(state)` sau `answer()`.

# ASSUMPTION: buoc VERIFY o day la BAN RUT GON (xem app/agent/decider.py) -
T09 se xay L0-L6 day du (`app/verify/`) va orchestrator se doi sang goi pipeline
do thay vi `basic_numeric_grounding_check`. Khong ha thap R1 trong luc cho:
the chua phan giai duoc VAN bi chan (BLOCK), chi la chua co du 7 lop.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.agent.decider import band_to_decision, basic_numeric_grounding_check, decide
from app.agent.narrator import LLMNarrator
from app.agent.planner import PlannedSection, Planner
from app.agent.playbooks import Playbook, PlaybookStore, get_playbook_store
from app.agent.renderer import render_narrative
from app.agent.router import Router
from app.agent.tools.action_tool import list_actions_with_eligibility
from app.agent.tools.registry import ToolRegistry, build_tool_registry
from app.contracts import (
    AgentEvent,
    AgentState,
    Band,
    Decision,
    Fact,
    Intent,
    LLMClient,
    TrustScore,
    Turn,
)
from app.errors import MissingEntityError
from app.llm.factory import build_llm_client
from app.llm.usage import UsageCounters
from app.prompts.loader import PromptLoader
from app.semantic.evidence import EvidenceSet
from app.settings import Settings, get_settings


def _merge_facts(
    fact_id: str, title: str, sub_facts: list[Fact], merge_keys: tuple[str, ...],
) -> Fact:
    """Ghep nhieu Fact (tinh tren cac dataset KHAC NHAU nhung cung mot section
    - vi du 'funnel' can ca `leads` tu campaign_daily va `applications` tu
    application) thanh MOT Fact, noi theo `merge_keys` (thuong la campaign_id).
    Neu `merge_keys` rong (section chi co MOT dong tong), ghep truc tiep."""
    base, *others = sub_facts
    merged_columns = list(base.columns)
    seen_col_names = {c.name for c in merged_columns}
    for other in others:
        for c in other.columns:
            if c.name not in seen_col_names and c.name != "_n_rows":
                merged_columns.append(c)
                seen_col_names.add(c.name)

    if not merge_keys:
        merged_row = dict(base.rows[0]) if base.rows else {"_ref": f"{fact_id}.r1"}
        for other in others:
            if other.rows:
                merged_row.update(
                    {k: v for k, v in other.rows[0].items() if k not in ("_ref", "_n_rows")}
                )
        merged_rows = [merged_row] if base.rows or any(o.rows for o in others) else []
    else:
        indexes = [
            {tuple(row.get(k) for k in merge_keys): row for row in other.rows}
            for other in others
        ]
        merged_rows = []
        for row in base.rows:
            merged = dict(row)
            key = tuple(row.get(k) for k in merge_keys)
            for idx in indexes:
                match = idx.get(key)
                if match:
                    merged.update(
                        {k: v for k, v in match.items() if k not in ("_ref", "_n_rows", *merge_keys)}
                    )
            merged_rows.append(merged)

    return Fact(
        fact_id=fact_id, title=title, query_id=f"{fact_id}-merged", sql="; ".join(
            f.sql for f in sub_facts
        ),
        columns=merged_columns, rows=merged_rows, row_count=len(merged_rows),
        caveats=list({c for f in sub_facts for c in f.caveats}),
    )


def _format_evidence_as_markdown_table(ev: EvidenceSet) -> str:
    """Fallback KHONG can LLM: bang markdown thuan tu EvidenceSet. Nhan cot
    lay tu `ColumnSpec.label` (nguon: catalog, `label_vi` trong metrics.yml/
    entities.yml) - KHONG co van tu tieng Viet tu do soan trong .py (R5)."""
    blocks: list[str] = []
    for fact in ev.facts:
        header = "| " + " | ".join(c.label for c in fact.columns) + " |"
        sep = "| " + " | ".join("---" for _ in fact.columns) + " |"
        rows = [
            "| " + " | ".join(str(row.get(c.name, "")) for c in fact.columns) + " |"
            for row in fact.rows
        ]
        blocks.append(f"### {fact.title}\n\n{header}\n{sep}\n" + "\n".join(rows))
    return "\n\n".join(blocks)


class Orchestrator:
    """Trien khai `app.contracts.Orchestrator`."""

    def __init__(
        self,
        settings: Settings,
        llm_client: LLMClient,
        prompts: PromptLoader,
        playbook_store: PlaybookStore,
        tools: ToolRegistry,
    ) -> None:
        self.settings = settings
        self.llm_client = llm_client
        self.prompts = prompts
        self.playbook_store = playbook_store
        self.tools = tools
        self.router = Router(tools.catalog, prompts)
        self.planner = Planner(tools.catalog)
        self.narrator = LLMNarrator(prompts, llm_client, playbook_store)
        self.max_llm_calls = int(settings.agent.get("max_llm_calls_per_question", 2))

    async def answer(
        self, question: str, *, session_id: str | None = None, history: list[Turn] | None = None,
    ) -> AgentState:
        state = AgentState(
            trace_id=uuid.uuid4(), question=question, session_id=session_id,
            history=history or [], started_at=datetime.now(UTC),
        )
        usage = UsageCounters()

        # ROUTE
        route_result = await self.router.route(self.llm_client, question, usage)
        state.intent = route_result.intent
        state.entities = route_result.entities
        state.route_confidence = route_result.confidence

        if state.intent == Intent.OUT_OF_SCOPE:
            await self._refuse(state, usage, abstain_code="OUT_OF_SCOPE",
                               detail="câu hỏi không liên quan tới dữ liệu chiến dịch/khách hàng")
            return state

        playbook = self.playbook_store.for_intent(state.intent.value)
        if playbook is None:
            await self._refuse(state, usage, abstain_code="NO_PLAYBOOK",
                               detail=f"chưa có phân tích cho loại câu hỏi '{state.intent.value}'")
            return state
        state.playbook = playbook.id

        if playbook.sql_guard is not None:
            # freeform: can sql_tool + 7 cua kiem tra (T12), chua duoc trien khai.
            await self._refuse(state, usage, abstain_code="FREEFORM_UNAVAILABLE",
                               detail="đường hỏi tự do (SQL có rào) sẽ có ở giai đoạn sau")
            return state

        # PLAN
        try:
            planned_sections = self.planner.plan(playbook, state.entities)
        except MissingEntityError as exc:
            await self._refuse(state, usage, abstain_code="MISSING_ENTITY", detail=str(exc))
            return state

        # COMPUTE + ANALYZE
        ev = self._build_evidence(planned_sections, playbook, state.trace_id)
        state.evidence = ev

        # NARRATE
        if usage.llm_calls >= self.max_llm_calls:
            state.narrative_final = _format_evidence_as_markdown_table(ev)
            state.checks = [basic_numeric_grounding_check([])]
            state.trust = TrustScore(value=0.5, band=Band.HEDGE,
                                     reasons=["het luot goi LLM - hien bang so tho"])
            state.decision = Decision.HEDGED
            self._finalize(state, usage, playbook)
            return state

        narrative = await self.narrator.narrate(playbook.id, ev, question)
        usage.add(tokens_in=0, tokens_out=0)
        state.narrative_template = narrative

        # RENDER truoc, VERIFY tren chinh chuoi hien thi cuoi cung
        rendered_text, unresolved = render_narrative(narrative, ev)
        state.narrative_final = rendered_text
        state.checks = [basic_numeric_grounding_check(unresolved)]

        t_high = float(self.settings.verify.get("t_high", 0.85))
        t_low = float(self.settings.verify.get("t_low", 0.60))
        state.trust = decide(state.checks, t_high=t_high, t_low=t_low)
        state.decision = band_to_decision(state.trust.band)

        self._finalize(state, usage, playbook)
        return state

    async def answer_stream(
        self, question: str, *, session_id: str | None = None, history: list[Turn] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Ban toi thieu, dung hop dong Protocol - StreamingVerifier day du
        (kiem chung theo khoi, khong lo the {{...}} nhap nhay) la viec cua T10."""
        state = await self.answer(question, session_id=session_id, history=history)
        yield AgentEvent(event="done", data={
            "trace_id": str(state.trace_id), "answer_markdown": state.narrative_final,
            "decision": state.decision.value,
        })

    def _finalize(self, state: AgentState, usage: UsageCounters, playbook: Playbook) -> None:
        state.llm_calls = usage.llm_calls
        state.tokens_in = usage.tokens_in
        state.tokens_out = usage.tokens_out
        state.prompt_version = playbook.prompt
        state.metrics_version = self.tools.catalog.version

    async def _refuse(
        self, state: AgentState, usage: UsageCounters, *, abstain_code: str, detail: str,
    ) -> None:
        """Tu choi/lam ro qua chinh prompt T3 (`refuse_out_of_scope.yaml`) -
        KHONG soan cau tieng Viet trong .py (R5). Day la lan goi LLM DUY NHAT
        cho nhanh nay, nen van trong ngan sach 2 luot/cau hoi ke ca khi ROUTE
        da dung 1 luot."""
        state.block_reason = detail
        if usage.llm_calls >= self.max_llm_calls:
            state.decision = Decision.ABSTAINED
            state.trust = TrustScore(value=0.0, band=Band.ABSTAIN, reasons=[detail])
            return

        rendered = self.prompts.render(
            "refuse_out_of_scope", question=state.question,
            abstain_code=abstain_code, detail=detail, raw_numbers=None,
        )
        text = await self.llm_client.complete(
            rendered.messages, temperature=rendered.params.get("temperature", 0.1),
            max_tokens=rendered.params.get("max_tokens", 250),
        )
        usage.add(tokens_in=0, tokens_out=0)
        state.narrative_final = text
        state.decision = Decision.ABSTAINED
        state.trust = TrustScore(value=0.0, band=Band.ABSTAIN, reasons=[detail])
        state.llm_calls = usage.llm_calls
        state.prompt_version = "refuse_out_of_scope"

    def _build_evidence(
        self, planned_sections: list[PlannedSection], playbook: Playbook, trace_id: uuid.UUID,
    ) -> EvidenceSet:
        ev = EvidenceSet(
            evidence_id=f"ev_{trace_id.hex[:8]}", generated_at=datetime.now(UTC),
            data_version="unknown",
        )
        segments_cache: list[dict[str, object]] | None = None

        for i, planned in enumerate(planned_sections, start=1):
            fact_id = planned.section.fact_id or f"F{i}"

            if planned.dataset_requests:
                try:
                    n_reqs = len(planned.dataset_requests)
                    sub_facts = [
                        self.tools.metric_tool.run(
                            dr.request,
                            fact_id if n_reqs == 1 else f"{fact_id}_{j}",
                            planned.section.label_vi,
                            dataset_override=dr.dataset_override,
                        )
                        for j, dr in enumerate(planned.dataset_requests, start=1)
                    ]
                    fact = (
                        sub_facts[0] if len(sub_facts) == 1
                        else _merge_facts(fact_id, planned.section.label_vi, sub_facts,
                                          planned.merge_keys)
                    )
                except Exception as exc:
                    ev.assumptions.append(
                        f"Không tính được phần '{planned.section.label_vi}': {exc}"
                    )
                    continue
                if planned.section.skip_if_empty and fact.row_count == 0:
                    continue
                ev.facts.append(fact)
                for c in fact.caveats:
                    if c not in ev.caveats:
                        ev.caveats.append(c)
                continue

            if planned.section.source == "actions":
                if segments_cache is None:
                    from app.agent.tools.segment_tool import build_segment_table

                    segments_cache = build_segment_table()
                actions = list_actions_with_eligibility(
                    self.tools.metric_tool.runner, segments=segments_cache,
                )
                eligible = [a for a in actions if a["eligible"]]
                if planned.section.min_priority is not None:
                    eligible = [a for a in eligible if a["priority"] >= planned.section.min_priority]
                if planned.section.max_items is not None:
                    eligible = eligible[: planned.section.max_items]
                ev.actions.extend(eligible)
            # "sql_tool"/"static"/"derived": chua trien khai day du o T08 -
            # bo qua section, ghi lai trong assumptions de khong am tham mat noi dung.
            elif planned.section.source is not None:
                ev.assumptions.append(
                    f"Phần '{planned.section.label_vi}' (nguồn '{planned.section.source}') "
                    "chưa được tính ở giai đoạn này."
                )

        for extra in playbook.required_caveats:
            text_vi = extra.get("text_vi")
            if text_vi and text_vi.strip() not in ev.caveats:
                ev.caveats.append(text_vi.strip())

        return ev


def build_orchestrator(settings: Settings | None = None) -> Orchestrator:
    """Diem lap rap - dung trong main.py/T10 va trong test/CLI (T08)."""
    settings = settings or get_settings()
    tools = build_tool_registry()
    usage = UsageCounters()
    llm_client = build_llm_client(settings, usage)
    prompts = PromptLoader()
    playbook_store = get_playbook_store()
    return Orchestrator(settings, llm_client, prompts, playbook_store, tools)


__all__ = ["Orchestrator", "build_orchestrator"]
