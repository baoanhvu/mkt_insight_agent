"""Kiem tra app/agent/streaming.py::StreamingVerifier va
Orchestrator.answer_stream - T10. Xem docs/15-streaming.md muc 15.10 va
docs/17-implementation-guide.md T10.
"""

from __future__ import annotations

import datetime as dt
import random
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.agent.orchestrator import Orchestrator, build_orchestrator
from app.agent.streaming import StreamingVerifier
from app.contracts import ColumnSpec, Fact
from app.semantic.catalog import get_catalog
from app.semantic.evidence import EvidenceSet
from app.settings import get_settings

_NARRATIVE = (
    "### Kết luận\n\n"
    "Chiến dịch {{F1.r1.campaign_id}} có ROMI {{F1.r1.romi}} và lợi nhuận "
    "ròng {{F1.r1.loi_nhuan}}.\n\n"
    "### Phễu\n\n"
    "Tỷ lệ duyệt đạt {{F1.r1.ty_le_duyet}} trong kỳ báo cáo.\n"
)


@pytest.fixture
def evidence() -> EvidenceSet:
    fact = Fact(
        fact_id="F1", title="ROMI theo chien dich", query_id="q1", sql="SELECT ...",
        columns=[
            ColumnSpec(name="campaign_id", label="Chien dich", unit="text", format=""),
            ColumnSpec(name="romi", label="ROMI", unit="ratio", format="0.00"),
            ColumnSpec(name="ty_le_duyet", label="Ty le duyet", unit="percent", format="0.0%"),
            ColumnSpec(name="loi_nhuan", label="Loi nhuan", unit="vnd", format="#,##0"),
        ],
        rows=[{
            "_ref": "F1.r1", "campaign_id": "CMP-ZL-RL1", "romi": 6.201503,
            "ty_le_duyet": 0.488, "loi_nhuan": 392498488.0,
        }],
        row_count=1,
    )
    return EvidenceSet(
        evidence_id="ev1", generated_at=dt.datetime.now(), data_version="etl_run_1", facts=[fact],
    )


def _random_chunks(text_: str, n: int, seed: int) -> list[str]:
    """Cat `text_` thanh `n` manh o cac vi tri NGAU NHIEN (co the roi dung
    giua mot the {{...}}) - mo phong token LLM khong biet ranh gioi ngu nghia."""
    rng = random.Random(seed)
    cut_points = sorted(rng.randint(0, len(text_)) for _ in range(n - 1))
    bounds = [0, *cut_points, len(text_)]
    return [text_[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]


def test_streaming_never_leaks_tags(evidence: EvidenceSet) -> None:
    """Sinh 500 cach cat token khac nhau cho CUNG mot van ban - khong lan nao
    duoc mot block.md chua '{{' hoac '}}' (BAT KE khoi do verified hay khong,
    vi block khong dat thi md=None)."""
    catalog = get_catalog()
    for seed in range(500):
        verifier = StreamingVerifier(evidence, catalog)
        events = []
        for chunk in _random_chunks(_NARRATIVE, n=7, seed=seed):
            events.extend(verifier.feed(chunk))
        events.extend(verifier.finish())
        for ev in events:
            md = ev.data.get("md")
            if md is not None:
                assert "{{" not in md and "}}" not in md, (seed, md)


def test_streaming_verified_blocks_reconstruct_rendered_text(evidence: EvidenceSet) -> None:
    """Khi TAT CA the deu phan giai duoc, ghep md cua cac khoi verified=True
    theo dung thu tu seq phai cho ra CHINH XAC van ban da render toan bo."""
    verifier = StreamingVerifier(evidence, get_catalog())
    events = []
    for chunk in _random_chunks(_NARRATIVE, n=5, seed=1):
        events.extend(verifier.feed(chunk))
    events.extend(verifier.finish())

    assert all(ev.data["verified"] for ev in events)
    joined = "".join(ev.data["md"] for ev in events)
    expected, unresolved = evidence.substitute(_NARRATIVE)
    assert unresolved == []
    assert joined == expected


def test_streaming_blocks_ungrounded(evidence: EvidenceSet) -> None:
    """The tham chieu mot fact_id KHONG TON TAI trong evidence -> khoi do
    verified=False va md=None (khong duoc de lot chuoi '{{...}}' ra ngoai)."""
    catalog = get_catalog()
    verifier = StreamingVerifier(evidence, catalog)
    narrative = "ROMI của chiến dịch bịa là {{F99.r1.romi}}.\n\n"
    events = list(verifier.feed(narrative)) + list(verifier.finish())

    assert events, "phai co it nhat mot block event"
    assert not any(ev.data["verified"] for ev in events)
    assert all(ev.data["md"] is None for ev in events)
    assert any(ev.data.get("reason") == "unresolved_tag" for ev in events)


def _skip_if_unreachable() -> None:
    try:
        engine = create_engine(get_settings().database.url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


class FakeLLM:
    """Giong het FakeLLM cua test_orchestrator.py - tra ve mot cau tra loi
    CO KIEM SOAT, chia thanh nhieu manh khi stream() de that su di qua
    StreamingVerifier.feed() nhieu lan thay vi mot lan duy nhat."""

    def __init__(self, response: str, chunk_size: int = 12) -> None:
        self.response = response
        self.chunk_size = chunk_size
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        return self.response

    async def stream(self, messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        self.calls.append(messages)
        for i in range(0, len(self.response), self.chunk_size):
            yield self.response[i : i + self.chunk_size]


@pytest.fixture
def orchestrator() -> Orchestrator:
    _skip_if_unreachable()
    return build_orchestrator()


def _install_fake_llm(orch: Orchestrator, response: str) -> FakeLLM:
    fake = FakeLLM(response)
    orch.llm_client = fake  # type: ignore[assignment]
    orch.narrator.llm_client = fake  # type: ignore[assignment]
    return fake


async def test_invocations_matches_stream(orchestrator: Orchestrator) -> None:
    """BAT BUOC (docs/15 muc 15.10, docs/17 T10): answer() va answer_stream()
    ghep lai phai cho CUNG MOT markdown."""
    response = (
        "Hai chiến dịch đang lỗ: {{F4.r1.campaign_name}} với ROMI {{F4.r1.romi}} "
        "và {{F4.r2.campaign_name}} với ROMI {{F4.r2.romi}}."
    )
    _install_fake_llm(orchestrator, response)
    baseline = await orchestrator.answer("Chiến dịch nào đang lỗ?")

    _install_fake_llm(orchestrator, response)
    joined_blocks: list[str] = []
    async for ev in orchestrator.answer_stream("Chiến dịch nào đang lỗ?"):
        if ev.event == "block" and ev.data.get("md") is not None:
            joined_blocks.append(ev.data["md"])

    assert "".join(joined_blocks) == baseline.narrative_final


async def test_progress_monotonic(orchestrator: Orchestrator) -> None:
    _install_fake_llm(orchestrator, "{{F4.r1.romi}}")
    progresses: list[float] = []
    async for ev in orchestrator.answer_stream("Chiến dịch nào đang lỗ?"):
        if ev.event == "stage":
            progresses.append(ev.data["progress"])

    assert progresses == sorted(progresses)
    assert progresses[-1] == pytest.approx(1.0)


async def test_playbook_override_label(orchestrator: Orchestrator) -> None:
    """Playbook campaign_overview phai phat nhan "Đang tạo dashboard hiệu quả
    chiến dịch" cho giai doan computing (config/stages.yaml playbook_overrides)."""
    _install_fake_llm(orchestrator, "{{F4.r1.romi}}")
    labels: dict[str, str] = {}
    async for ev in orchestrator.answer_stream("Chiến dịch nào đang lỗ?"):
        if ev.event == "stage":
            labels[ev.data["stage"]] = ev.data["label"]

    assert labels["computing"] == "Đang tạo dashboard hiệu quả chiến dịch"
    assert labels["narrating"] == "Đang tóm tắt kết quả từng chiến dịch"


async def test_dashboard_question_routes_without_llm_call(orchestrator: Orchestrator) -> None:
    """Cau hoi "Tạo dashboard" phai khop luat regex (0 loi goi LLM cho ROUTE)
    va phat dung nhan cua playbook campaign_overview - dung nhu vi du curl
    trong docs/17 T10."""
    fake = _install_fake_llm(orchestrator, "{{F1.r1.romi}}")
    stages: list[dict[str, object]] = []
    async for ev in orchestrator.answer_stream("Tạo dashboard"):
        if ev.event == "stage":
            stages.append(ev.data)

    assert len(fake.calls) == 1  # chi mot lan goi (NARRATE) - ROUTE khop luat
    computing = next(s for s in stages if s["stage"] == "computing")
    assert computing["label"] == "Đang tạo dashboard hiệu quả chiến dịch"


async def test_out_of_scope_question_ends_with_done_event(orchestrator: Orchestrator) -> None:
    _install_fake_llm(orchestrator, "Không liên quan tới dữ liệu marketing.")
    events = [ev async for ev in orchestrator.answer_stream("Thời tiết Hà Nội hôm nay thế nào?")]
    assert events[-1].event == "done"
    assert events[-1].data["decision"] == "ABSTAINED"
