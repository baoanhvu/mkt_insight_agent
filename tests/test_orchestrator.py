"""Kiem tra app/agent/orchestrator.py end-to-end. Xem
docs/17-implementation-guide.md T08.

BAT BUOC:
    st = await build_orchestrator().answer('Chiến dịch nào đang lỗ?')
    assert st.llm_calls <= 2
    assert 'Broker' in st.narrative_final

Can Postgres cua profile test (docker-compose.dev.yml, du lieu da nap qua T02).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.agent.orchestrator import Orchestrator, build_orchestrator
from app.contracts import Band, Decision, Intent
from app.settings import get_settings


class FakeLLM:
    """LLM gia lap CO KIEM SOAT - khac MockLLMClient (T07) vi test o day can
    biet CHINH XAC narrative tra ve de kiem tra co the {{...}} duoc thay dung
    hay khong, khong phu thuoc vao fixture khop hash."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        return self.response

    async def stream(self, messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        self.calls.append(messages)
        yield self.response


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


def _install_fake_llm(orch: Orchestrator, response: str) -> FakeLLM:
    fake = FakeLLM(response)
    orch.llm_client = fake  # type: ignore[assignment]
    orch.narrator.llm_client = fake  # type: ignore[assignment]
    return fake


async def test_losing_campaigns_question_matches_required_acceptance_criteria(
    orchestrator: Orchestrator,
) -> None:
    """BAT BUOC (docs/17 T08): llm_calls <= 2, 'Broker' trong narrative_final."""
    _install_fake_llm(
        orchestrator,
        "Hai chiến dịch đang lỗ: {{F4.r1.campaign_name}} với ROMI {{F4.r1.romi}} "
        "và {{F4.r2.campaign_name}} với ROMI {{F4.r2.romi}}.",
    )
    st = await orchestrator.answer("Chiến dịch nào đang lỗ?")

    assert st.llm_calls <= 2, st.llm_calls
    assert "Broker" in st.narrative_final, st.narrative_final
    assert st.decision == Decision.ANSWERED
    assert st.trust is not None and st.trust.value == pytest.approx(1.0)


async def test_router_matches_by_rule_without_calling_llm(orchestrator: Orchestrator) -> None:
    """"Chiến dịch nào đang lỗ?" phai khop bang luat regex (0 goi LLM cho
    buoc ROUTE) - day la ly do llm_calls chi la 1 (chi NARRATE), khong phai 2."""
    fake = _install_fake_llm(orchestrator, "{{F4.r1.romi}}")
    await orchestrator.answer("Chiến dịch nào đang lỗ?")
    assert len(fake.calls) == 1  # CHI mot lan goi (NARRATE) - ROUTE khop luat


async def test_evidence_has_addressable_facts_for_losing_campaigns(
    orchestrator: Orchestrator,
) -> None:
    _install_fake_llm(orchestrator, "{{F4.r1.romi}}")
    st = await orchestrator.answer("Chiến dịch nào đang lỗ?")
    assert st.evidence is not None
    losers_fact = next(f for f in st.evidence.facts if f.fact_id == "F4")
    campaign_ids = {row["campaign_id"] for row in losers_fact.rows}
    assert campaign_ids == {"CMP-PTN-BRK01", "CMP-PTN-MOMO"}  # 2 chien dich am ROMI


async def test_funnel_section_merges_two_datasets_correctly(orchestrator: Orchestrator) -> None:
    """Section 'funnel' tron chi so tu dataset application (`applications`)
    va campaign_daily (`leads`) - Planner phai tach thanh hai truy van va
    Orchestrator phai ghep lai theo campaign_id."""
    _install_fake_llm(orchestrator, "{{F2.r1.leads}}")
    st = await orchestrator.answer("Chiến dịch nào đang lỗ?")
    funnel_fact = next(f for f in st.evidence.facts if f.fact_id == "F2")
    col_names = {c.name for c in funnel_fact.columns}
    assert {"leads", "applications", "disbursed_loans"} <= col_names
    for row in funnel_fact.rows:
        assert row["leads"] is not None
        assert row["applications"] is not None


async def test_diagnosis_question_routes_with_campaign_entity(orchestrator: Orchestrator) -> None:
    _install_fake_llm(orchestrator, "{{F1.r1.romi}}")
    st = await orchestrator.answer("Vì sao Broker Network lỗ?")
    assert st.intent == Intent.CAMPAIGN_DIAGNOSIS
    assert st.entities.get("campaign_id") == ["CMP-PTN-BRK01"]
    assert st.evidence is not None
    verdict_fact = next(f for f in st.evidence.facts if f.fact_id == "F1")
    assert verdict_fact.rows[0]["campaign_id"] == "CMP-PTN-BRK01"


async def test_out_of_scope_question_is_refused_not_answered(orchestrator: Orchestrator) -> None:
    _install_fake_llm(orchestrator, "Không liên quan tới dữ liệu marketing.")
    st = await orchestrator.answer("Thời tiết Hà Nội hôm nay thế nào?")
    assert st.intent == Intent.OUT_OF_SCOPE
    assert st.decision == Decision.ABSTAINED
    assert st.trust is not None and st.trust.band == Band.ABSTAIN


async def test_unresolved_tag_blocks_the_answer(orchestrator: Orchestrator) -> None:
    """R1: mot the khong phan giai duoc (fact_id bia ra) PHAI chan cau tra
    loi, khong duoc de lot mot cau van co chu so khong co dia chi."""
    _install_fake_llm(orchestrator, "ROMI là {{F99.r1.romi}}.")
    st = await orchestrator.answer("Chiến dịch nào đang lỗ?")
    assert st.decision == Decision.BLOCKED
    assert st.trust is not None and st.trust.value == 0.0
    assert "{{F99.r1.romi}}" in st.narrative_final  # giu nguyen the, khong am tham xoa


async def test_llm_call_budget_is_never_exceeded(orchestrator: Orchestrator) -> None:
    fake = _install_fake_llm(orchestrator, "{{F1.r1.romi}}")
    st = await orchestrator.answer("Chiến dịch nào có ROMI cao nhất?")
    assert st.llm_calls <= 2
    assert len(fake.calls) <= 2


async def test_missing_required_entity_triggers_refusal_not_crash(
    orchestrator: Orchestrator,
) -> None:
    """campaign_diagnosis yeu cau entity campaign_id - hoi mot cau chan doan
    KHONG neu ten chien dich nao phai duoc lam ro, khong duoc crash."""
    _install_fake_llm(orchestrator, "Bạn muốn xem chiến dịch nào?")
    st = await orchestrator.answer("Vì sao chiến dịch này lỗ?")
    assert st.decision in (Decision.ABSTAINED, Decision.ANSWERED)
