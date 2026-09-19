"""Hop dong giua cac module.

Day la tai lieu thiet ke o muc class/function, nhung viet bang Python nen `mypy`
kiem tra duoc va no khong bao gio noi doi. Xem docs/16-dev-readiness.md muc 16.3.

QUY TAC:
  - File nay KHONG import bat ky module nao khac trong `app`. No la la cua cay
    phu thuoc, nen moi module deu import duoc no ma khong sinh vong tron.
  - Moi Protocol o day la mot ranh gioi co the chia viec. Hai nguoi lam hai ben
    cua mot Protocol khong can noi chuyen voi nhau.
  - Doi mot Protocol la thay doi PHA VO. Phai bao cho ca hai ben.

Thu tu doc: kieu du lieu loi (muc 1-4) -> Protocol (muc 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, AsyncIterator, Literal, Protocol, Sequence
from uuid import UUID

# =============================================================================
# 1. SEMANTIC LAYER
# =============================================================================

Unit = Literal["count", "vnd", "ratio", "percent", "days", "months",
               "seconds", "years", "rate_pct_month", "text"]

FilterOp = Literal["eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "between"]


@dataclass(frozen=True, slots=True)
class Dimension:
    """Mot chieu cat du lieu. Nap tu config/semantic/entities.yml."""
    name: str
    column: str
    label_vi: str
    datasets: tuple[str, ...]
    type: Literal["text", "boolean", "date", "number"] = "text"
    label_column: str | None = None
    allowed_values: tuple[str, ...] | None = None
    ordered: tuple[str, ...] | None = None
    caveat_vi: str | None = None
    note_vi: str | None = None


@dataclass(frozen=True, slots=True)
class Metric:
    """Mot chi so. Nap tu config/semantic/metrics.yml.

    `sql` la BIEU THUC TONG HOP (vi du "SUM(net_profit)"), khong phai cau SELECT
    day du. Compiler boc no vao SELECT ... FROM ... GROUP BY ...
    """
    name: str
    label_vi: str
    dataset: str
    unit: Unit
    format: str
    sql: str | None = None                  # None khi `computed_by` khac None
    computed_by: str | None = None          # duong dan ham Python, vi du "app.analytics.clv.estimate_clv"
    description_vi: str = ""
    higher_is_better: bool | None = None
    min_sample_size: int | None = None
    caveat_vi: str | None = None
    thresholds: dict[str, dict[str, float]] | None = None
    allowed_dimensions: tuple[str, ...] = ()
    requires_confidence_interval: bool = False
    requires_assumptions: bool = False
    must_report_with: tuple[str, ...] = ()  # chi so BAT BUOC bao cao kem
    reference: dict[str, Any] | None = None # gia tri da kiem chung -> test_metrics_contract


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    table: str
    grain: str
    default_date_column: str
    description_vi: str = ""
    caveat_vi: str | None = None
    row_count_expected: int | None = None


@dataclass(frozen=True, slots=True)
class Filter:
    dimension: str
    op: FilterOp
    value: Any


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end_exclusive: date


@dataclass(frozen=True, slots=True)
class MetricRequest:
    """Thu DUY NHAT ma LLM duoc phat ra de truy van du lieu.

    Moi truong deu duoc doi chieu voi catalog TRUOC KHI cham toi database.
    Truong khong hop le -> raise, khong bao gio lot xuong SQL.
    """
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    date_range: DateRange | None = None
    order_by: str | None = None
    order_desc: bool = True
    limit: int = 100
    having: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    """SQL da sinh. `query_id` la dia chi cua truy van trong EvidenceSet."""
    query_id: str
    sql: str
    params: dict[str, Any]
    metrics: tuple[Metric, ...]
    dimensions: tuple[Dimension, ...]
    caveats: tuple[str, ...] = ()


# =============================================================================
# 2. EVIDENCE  - cau noi giua so lieu va ngon ngu
# =============================================================================

@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    label: str
    unit: Unit
    format: str
    higher_is_better: bool | None = None


@dataclass(frozen=True, slots=True)
class Cell:
    """Mot o du lieu co dia chi. Dau ra cua EvidenceSet.resolve()."""
    ref: str                    # "F1.r3.romi"
    value: Any
    unit: Unit
    format: str
    formatted: str              # chuoi da dinh dang vi-VN, vi du "6,20"


@dataclass(slots=True)
class Fact:
    """Ket qua mot truy van. Moi dong co khoa `_ref` dang "F1.r3"."""
    fact_id: str                # "F1"
    title: str
    query_id: str
    sql: str
    columns: list[ColumnSpec]
    rows: list[dict[str, Any]]
    row_count: int
    caveats: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DerivedFact:
    """Gia tri do CODE tinh tu cac Fact khac. KHONG BAO GIO do LLM tinh."""
    fact_id: str                # "D1"
    expr: str                   # "F1.r1.romi / F1.r2.romi"
    value: Any
    label_vi: str
    unit: Unit
    formatted: str


@dataclass(slots=True)
class Comparison:
    """Mot phep so sanh DA CHAY KIEM DINH.

    Narrator chi duoc dung tu so sanh hon kem khi `significant` la True.
    Lop L4 kiem tra dieu do sau khi sinh van ban.
    """
    left: str                   # "F1.r1"
    right: str                  # "F1.r2"
    metric: str
    diff: float
    p_value: float
    ci: tuple[float, float]
    effect_size: float
    n_left: int
    n_right: int
    significant: bool
    verdict_vi: str
    test_name: str = "two_proportion_ztest"


@dataclass(slots=True)
class EvidenceSet:
    """Tap bang chung day du cho mot cau tra loi.

    Day la thu DUY NHAT Narrator duoc nhin thay. No khong nhin thay database,
    khong nhin thay schema, khong nhin thay catalog.
    """
    evidence_id: str
    generated_at: datetime
    data_version: str           # etl_run_id -> dung de vo hieu cache
    facts: list[Fact] = field(default_factory=list)
    derived: list[DerivedFact] = field(default_factory=list)
    comparisons: list[Comparison] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    def resolve(self, ref: str) -> Cell | None:
        """'F1.r3.romi' -> Cell. None neu khong ton tai.

        None la tin hieu cho lop L2 CHAN cau tra loi. Khong bao gio tra ve
        gia tri mac dinh hay chuoi rong.
        """
        raise NotImplementedError

    def substitute(self, text: str) -> tuple[str, list[str]]:
        """Thay moi {{ref}} bang chuoi da dinh dang.

        Returns:
            (van_ban_da_thay, danh_sach_ref_khong_phan_giai_duoc)
        """
        raise NotImplementedError

    def matches_any_cell(self, value: float, policy: NumericPolicy) -> bool:
        """Co o nao trong evidence khop `value` theo `policy` khong."""
        raise NotImplementedError

    def all_string_values(self) -> set[str]:
        """Moi gia tri chuoi xuat hien trong evidence. Dung cho lop L3."""
        raise NotImplementedError


# =============================================================================
# 3. KIEM CHUNG
# =============================================================================

class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    BLOCK = "BLOCK"


class Band(StrEnum):
    PASS = "PASS"
    HEDGE = "HEDGE"
    ABSTAIN = "ABSTAIN"
    BLOCKED = "BLOCKED"


class Decision(StrEnum):
    PENDING = "PENDING"
    ANSWERED = "ANSWERED"
    HEDGED = "HEDGED"
    ABSTAINED = "ABSTAINED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class NumericPolicy:
    """Chinh sach so khop so. Khai bao trong config/verify.yaml -> numeric.policy."""
    mode: Literal["exact", "round", "rel_tol", "abs_tol"]
    decimals: int = 2
    tol: float = 0.0
    aliases: tuple[str, ...] = ()


@dataclass(slots=True)
class CheckResult:
    name: str
    passed: bool
    score: float                # 0..1
    severity: Severity
    details: dict[str, Any] = field(default_factory=dict)
    message_vi: str | None = None


@dataclass(slots=True)
class TrustScore:
    value: float
    band: Band
    components: dict[str, CheckResult] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class JudgeResult:
    """Ket qua lop L5. Ba nhan thay vi mot diem - xem ADR-003."""
    entailment_rate: float
    neutral_rate: float
    contradiction_rate: float
    grounding_score: float
    claims: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    prompt_version: str = ""
    latency_ms: int = 0


# =============================================================================
# 4. AGENT
# =============================================================================

class Intent(StrEnum):
    CAMPAIGN_OVERVIEW = "campaign_overview"
    CAMPAIGN_DIAGNOSIS = "campaign_diagnosis"
    FUNNEL_ANALYSIS = "funnel_analysis"
    CUSTOMER_PERSONA = "customer_persona"
    SEGMENT_DEEP_DIVE = "segment_deep_dive"
    CLV_ACTIONS = "clv_actions"
    RISK_FRAUD = "risk_fraud"
    DATA_QUESTION = "data_question"
    FREEFORM = "freeform"
    OUT_OF_SCOPE = "out_of_scope"


class Stage(StrEnum):
    INTAKE = "intake"
    ROUTING = "routing"
    PLANNING = "planning"
    COMPUTING = "computing"
    ANALYZING = "analyzing"
    NARRATING = "narrating"
    VERIFYING = "verifying"
    RENDERING = "rendering"
    JUDGING = "judging"


@dataclass(slots=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str
    trace_id: UUID | None = None


@dataclass(slots=True)
class AgentState:
    """Trang thai mot luot tra loi.

    Moi buoc cua Orchestrator la mot ham `step(state) -> state`. Nho vay tung
    buoc test duoc doc lap, va mot phien tai hien lai duoc tu ops.agent_trace.
    """
    trace_id: UUID
    question: str
    session_id: str | None = None
    history: list[Turn] = field(default_factory=list)
    locale: str = "vi"

    intent: Intent | None = None
    entities: dict[str, list[str]] = field(default_factory=dict)
    playbook: str | None = None
    route_confidence: float = 0.0

    metric_requests: list[MetricRequest] = field(default_factory=list)
    evidence: EvidenceSet | None = None
    analyses: dict[str, Any] = field(default_factory=dict)

    narrative_template: str | None = None   # van con the {{F1.r1.romi}}
    narrative_final: str | None = None      # da thay the

    checks: list[CheckResult] = field(default_factory=list)
    trust: TrustScore | None = None
    decision: Decision = Decision.PENDING
    block_reason: str | None = None

    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    started_at: datetime | None = None
    prompt_version: str = ""
    metrics_version: str = ""
    regeneration_attempts: int = 0


@dataclass(slots=True)
class AgentEvent:
    """Mot su kien SSE. Xem docs/15-streaming.md muc 15.3."""
    event: Literal["stage", "plan", "evidence", "table", "chart", "block",
                   "warning", "verified", "judge", "artifact", "done", "error"]
    data: dict[str, Any]
    seq: int = 0


@dataclass(slots=True)
class VerifiedBlock:
    """Mot khoi markdown da thay the the va da kiem chung.

    `md` la None khi khoi khong qua kiem chung. Khi do client hien mot o xam
    thay vi noi dung - KHONG BAO GIO hien roi rut lai.
    """
    seq: int
    raw: str
    md: str | None
    verified: bool
    numeric: CheckResult | None = None
    entity: CheckResult | None = None
    unresolved_tags: list[str] = field(default_factory=list)


# =============================================================================
# 5. PROTOCOL  - ranh gioi chia viec
# =============================================================================

class Catalog(Protocol):
    """Nap va tra cuu dinh nghia chi so. Nguon: config/semantic/*.yml."""
    version: str

    def metric(self, name: str) -> Metric: ...
    def dimension(self, name: str, dataset: str) -> Dimension: ...
    def dataset_of(self, metric_name: str) -> Dataset: ...
    def all_dimension_values(self) -> set[str]: ...
    def validate_against_db(self, engine: Any) -> list[str]:
        """Moi cot trong metrics.yml phai ton tai that. Tra ve danh sach loi."""
        ...


class QueryCompiler(Protocol):
    """MetricRequest -> CompiledQuery.

    BAT BIEN (test trong tests/test_semantic_compiler.py):
      1. Ten bang/cot CHI lay tu catalog, khong bao gio tu input
      2. Gia tri filter luon di qua bind parameter
      3. Luon co LIMIT
      4. Luon them COUNT(*) AS _n_rows
      5. ORDER BY chi nhan ten da co trong SELECT
    """
    def compile(self, req: MetricRequest) -> CompiledQuery: ...


class MetricRunner(Protocol):
    """Chay CompiledQuery va tra ve Fact co dia chi o."""
    def run(self, req: MetricRequest, fact_id: str, title: str) -> Fact: ...


class SQLGuard(Protocol):
    """Lop L0: kiem tra SQL do LLM sinh, tren CAY CU PHAP chu khong tren chuoi."""
    def validate(self, sql: str) -> GuardResult: ...
    async def explain(self, sql: str) -> dict[str, Any]: ...


@dataclass(slots=True)
class GuardResult:
    ok: bool
    sql_rewritten: str | None = None
    unbound_identifiers: list[str] = field(default_factory=list)
    forbidden_statements: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    limit_injected: bool = False


class Narrator(Protocol):
    """Sinh van ban co THE, khong co chu so.

    Xem prompts/narrate_*.yaml. Dau ra van con {{F1.r1.romi}} - viec thay the
    va kiem chung thuoc ve StreamingVerifier/Renderer.
    """
    async def narrate(self, playbook_id: str, ev: EvidenceSet,
                      question: str) -> str: ...
    async def narrate_stream(self, playbook_id: str, ev: EvidenceSet,
                             question: str) -> AsyncIterator[str]: ...


class Checker(Protocol):
    """Mot lop kiem chung.

    PHAI THUAN: khong I/O, khong goi LLM, khong doc file. Nho vay test duoc ma
    khong can database hay mang. Ngoai le duy nhat la Judge (L5), duoc danh dau
    bang `is_async = True`.
    """
    name: str
    severity: Severity
    is_async: bool

    def check(self, answer: str, ev: EvidenceSet) -> CheckResult: ...


class VerificationPipeline(Protocol):
    """Chay L0-L4 dong bo (< 50ms), dat lich L5 chay nen neu judge_async."""
    async def run(self, *, answer: str, evidence: EvidenceSet, question: str,
                  guard: GuardResult | None = None) -> TrustScore: ...
    async def run_judge_later(self, trace_id: UUID, answer: str,
                              evidence: EvidenceSet) -> JudgeResult: ...


class StatsEngine(Protocol):
    """Toan thuan tuy. Khong I/O.

    `bootstrap_mean_diff` dung seed CO DINH: cung cau hoi phai cho cung p-value,
    neu khong thi hai lan hoi giong nhau co the cho hai ket luan khac nhau ve y
    nghia thong ke.
    """
    def wilson_ci(self, successes: int, n: int,
                  conf: float = 0.95) -> tuple[float, float]: ...
    def two_proportion_ztest(self, x1: int, n1: int, x2: int,
                             n2: int) -> Comparison: ...
    def bootstrap_mean_diff(self, a: Sequence[float], b: Sequence[float],
                            n_boot: int = 2000, seed: int = 42) -> Comparison: ...
    def cohens_d(self, a: Sequence[float], b: Sequence[float]) -> float: ...


class SegmentBuilder(Protocol):
    """Gan moi khach vao dung mot phan khuc.

    BAT BIEN: tong so khach trong moi phan khuc = tong so khach trong bang.
    Khong duoc co '_unclassified' khac rong.
    """
    def build(self, rows: Sequence[dict[str, Any]]) -> dict[str, list[str]]: ...


class CLVEstimator(Protocol):
    """Uoc luong CLV. LUON tra ve khoang, khong bao gio tra ve mot diem.

    n < min_sample_size -> tra ve ket qua co `insufficient = True`, KHONG tra so.
    """
    def estimate(self, segment_stats: dict[str, Any]) -> CLVEstimate: ...


@dataclass(slots=True)
class CLVEstimate:
    point: float | None
    lower: float | None
    upper: float | None
    insufficient: bool = False
    reason: str | None = None
    assumptions: list[str] = field(default_factory=list)
    p_repeat_source: str = ""


class LLMClient(Protocol):
    """Goi model. Khong biet gi ve nghiep vu.

    Token bucket dat o CLIENT, khong dua vao viec bat loi 429: tran MaaS tinh
    chung ca tai khoan nen de dung tran moi lui se tao hieu ung bay dan.
    """
    async def complete(self, messages: list[dict[str, str]], *,
                       model: str | None = None,
                       temperature: float | None = None,
                       max_tokens: int | None = None,
                       response_format: Literal["text", "json"] = "text",
                       ) -> str: ...
    async def stream(self, messages: list[dict[str, str]],
                     **kwargs: Any) -> AsyncIterator[str]: ...


class PromptStore(Protocol):
    """Nap prompt tu YAML, hot-reload theo mtime.

    Parse loi -> GIU NGUYEN ban dang chay va ghi log. Mot file YAML hong khong
    bao gio duoc lam sap agent dang phuc vu.
    Jinja2 chi render `system` va `instructions`; `few_shots` chen NGUYEN VAN.
    """
    def get(self, prompt_id: str) -> dict[str, Any]: ...
    def render(self, prompt_id: str, **ctx: Any) -> RenderedPrompt: ...
    def validate(self, prompt_id: str) -> list[str]: ...


@dataclass(slots=True)
class RenderedPrompt:
    prompt_id: str
    version: str
    messages: list[dict[str, str]]
    params: dict[str, Any]


class TraceStore(Protocol):
    """Ghi ops.agent_trace. Ba cot bat buoc: prompt_version, model_name, profile."""
    async def save(self, state: AgentState) -> None: ...
    async def update_judge(self, trace_id: UUID, judge: JudgeResult) -> None: ...
    async def get(self, trace_id: UUID) -> dict[str, Any] | None: ...


class Orchestrator(Protocol):
    """Dieu phoi pipeline. KHONG viet SQL, KHONG goi DB truc tiep.

    `answer` va `answer_stream` phai cho ra CUNG MOT markdown khi ghep lai -
    tests/test_streaming.py::test_invocations_matches_stream khang dinh dieu do.
    """
    async def answer(self, question: str, *, session_id: str | None = None,
                     history: list[Turn] | None = None) -> AgentState: ...
    async def answer_stream(self, question: str, *, session_id: str | None = None,
                            history: list[Turn] | None = None,
                            ) -> AsyncIterator[AgentEvent]: ...
