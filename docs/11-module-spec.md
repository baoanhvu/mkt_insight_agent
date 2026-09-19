# 11 — Đặc tả module và mã nguồn

## 11.1 Cây thư mục

```
mkt_insight_agent/
├── main.py                        # ENTRYPOINT - AgentBase bat buoc ten file nay
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── .greennode.json                # {client_id, client_secret, agent_identity}
├── .env.example
├── .dockerignore
├── .gitignore
├── docker-compose.dev.yml         # Postgres cho test/CI
│
├── app/
│   ├── __init__.py
│   ├── settings.py                # 10.6
│   ├── logging_.py                # structlog + filter che bi mat
│   ├── errors.py                  # cay exception cua ung dung
│   ├── contracts.py               # Protocol giua cac module  (16.3)
│   │
│   ├── api/
│   │   ├── app_factory.py         # create_app() -> FastAPI
│   │   ├── deps.py                # dependency injection
│   │   ├── schemas.py             # pydantic DTO cho request/response
│   │   ├── routes_health.py       # /health /readyz /version
│   │   ├── routes_invocations.py  # /invocations  (quy uoc AgentBase)
│   │   ├── routes_chat.py         # /api/chat  (SSE)
│   │   ├── routes_dashboard.py    # /api/dashboard/*
│   │   ├── routes_segments.py     # /api/segments/*
│   │   ├── routes_actions.py      # /api/actions
│   │   ├── routes_trace.py        # /api/trace/{id}
│   │   └── routes_admin.py        # /api/admin/*
│   │
│   ├── agent/
│   │   ├── state.py               # AgentState  (06.2)
│   │   ├── orchestrator.py        # chay pipeline INTAKE..TRACE
│   │   ├── router.py              # phan loai intent
│   │   ├── planner.py             # playbook -> list[MetricRequest]
│   │   ├── narrator.py            # EvidenceSet -> van ban co the
│   │   ├── decider.py             # TrustScore -> Decision
│   │   ├── renderer.py            # thay the the -> so that
│   │   ├── streaming.py           # StreamingVerifier: kiem chung theo khoi  (15.4)
│   │   ├── stages.py              # nap config/stages.yaml, tinh progress   (15.2)
│   │   ├── playbooks.py           # nap config/playbooks/*.yml
│   │   └── tools/
│   │       ├── registry.py
│   │       ├── metric_tool.py
│   │       ├── sql_tool.py        # freeform co rao
│   │       ├── schema_tool.py
│   │       ├── stats_tool.py
│   │       ├── clv_tool.py
│   │       ├── segment_tool.py
│   │       └── export_tool.py
│   │
│   ├── semantic/
│   │   ├── models.py              # Metric, Dimension, Dataset, Filter, MetricRequest
│   │   ├── catalog.py             # nap + validate metrics.yml / entities.yml
│   │   ├── compiler.py            # MetricRequest -> CompiledQuery   (05.3)
│   │   └── evidence.py            # EvidenceSet, Fact, resolve(), substitute()
│   │
│   ├── data/
│   │   ├── engines.py             # 3 engine theo role  (03.3)
│   │   ├── repository.py          # thuc thi CompiledQuery -> Fact
│   │   ├── cache.py               # TTLCache + answer_cache trong DB
│   │   └── sqlguard.py            # sqlglot AST + schema binding  (L0)
│   │
│   ├── analytics/
│   │   ├── stats.py               # wilson_ci, two_proportion_ztest, bootstrap
│   │   ├── clv.py                 # estimate_clv  (06.5)
│   │   ├── segmentation.py        # SEGMENT_RULES + kmeans doi chung  (06.6)
│   │   ├── funnel.py
│   │   └── derive.py              # tinh khoi `derived` cua EvidenceSet
│   │
│   ├── verify/
│   │   ├── models.py              # CheckResult, TrustScore, Decision, Band
│   │   ├── pipeline.py            # chay L0..L6, tong hop
│   │   ├── numeric.py             # L2  (08.3)
│   │   ├── entity.py              # L3  (08.5)
│   │   ├── stats_guard.py         # L4  (08.4)
│   │   ├── judge.py               # L5  (08.6)
│   │   ├── consistency.py         # self-consistency cho freeform
│   │   └── vi_text.py             # tach cau, so vi-VN, marker so sanh/nhan qua
│   │
│   ├── llm/
│   │   ├── client.py              # OpenAI-compatible async + retry + rate limit
│   │   ├── mock.py                # provider "mock" cho test
│   │   └── usage.py               # dem token, dem luot goi
│   │
│   ├── prompts/
│   │   └── loader.py              # PromptLoader  (07.4)
│   │
│   ├── telemetry/
│   │   ├── trace.py               # dung ban ghi trace
│   │   └── store.py               # ghi ops.agent_trace
│   │
│   └── web/
│       ├── formatting.py          # fmt_vnd, fmt_pct...  (09.8)
│       ├── templates/
│       │   ├── base.html
│       │   ├── index.html
│       │   ├── _kpi.html
│       │   ├── _dashboard.html
│       │   ├── _chat.html         # rang buoc 60vh o day
│       │   ├── _evidence_panel.html
│       │   └── admin/{prompts,metrics,quality}.html
│       └── static/
│           ├── app.js  chat.js  charts.js  format.js
│           └── styles.css
│
├── prompts/                       # 07.2 - sua duoc, khong can build
│   ├── route_intent.yaml
│   ├── narrate_campaign_overview.yaml
│   ├── narrate_campaign_diagnosis.yaml
│   ├── narrate_funnel.yaml
│   ├── narrate_persona.yaml
│   ├── narrate_clv_actions.yaml
│   ├── judge_grounding.yaml
│   ├── clarify_question.yaml
│   └── refuse_out_of_scope.yaml
│
├── config/                        # 10.1
│   ├── app.yaml
│   ├── profiles/{local,greennode,test}.yaml
│   ├── secrets.example.yaml
│   ├── semantic/{metrics.yml,entities.yml}
│   ├── playbooks/*.yml
│   ├── verify.yaml
│   ├── stages.yaml                # nhan tien trinh streaming  (15.2)
│   └── analytics.yaml
│
├── etl/
│   ├── load_excel.py
│   ├── build_marts.py
│   ├── dq_checks.py
│   └── sql/{00_roles.sql,01_ddl_raw.sql,02_ddl_mart.sql,03_ddl_ops.sql}
│
├── evals/
│   ├── golden/qa_set.yaml         # 100 ca
│   ├── run_eval.py
│   ├── metrics.py                 # execution accuracy, grounding rate...
│   └── report.py
│
├── tests/
│   ├── conftest.py
│   ├── test_semantic_compiler.py
│   ├── test_metrics_contract.py   # doi chieu gia tri tham chieu 02.4
│   ├── test_numeric_grounding.py
│   ├── test_stats_guard.py
│   ├── test_sqlguard.py
│   ├── test_clv.py
│   ├── test_segmentation.py
│   ├── test_etl_invariants.py
│   └── e2e/test_ui_chat_height.py
│
├── scripts/
│   ├── bootstrap_db.ps1
│   ├── run_local.ps1
│   └── deploy_greennode.ps1
│
├── data/
│   ├── full_schema_mock_v2.xlsx
│   └── parquet/
│
├── .claude/skills/                # greennode-agentbase-skills (12.1)
└── docs/                          # tai lieu nay
```

## 11.2 `main.py` — hợp đồng với AgentBase

Hai yêu cầu cứng của AgentBase Runtime: lắng nghe **cổng 8080** và có **`GET /health` trả 200**. Ngoài hai điều đó, mọi route khác là tự do — đó là lý do ta phục vụ được cả UI web trong cùng container.

```python
# main.py  -- ten file nay la bat buoc theo scaffold cua AgentBase
import uvicorn
from app.api.app_factory import create_app

app = create_app()          # FastAPI: /health, /invocations, /, /api/*

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_config=None)
```

Ta dùng FastAPI thuần thay vì `GreenNodeAgentBaseApp` của SDK, vì cần toàn quyền gắn thêm route cho UI, SSE và trang admin. Tài liệu nền tảng nói rõ `POST /invocations` là **quy ước của SDK, không phải yêu cầu của nền tảng** — agent không dùng SDK được phép tự định nghĩa đường dẫn. Ta vẫn giữ `/invocations` đúng quy ước để cổng Zalo hoặc bất kỳ client chuẩn nào gọi được.

Header do nền tảng truyền vào và ta đọc:

| Header | Dùng làm gì |
|---|---|
| `X-GreenNode-AgentBase-Session-Id` | `AgentState.session_id` |
| `X-GreenNode-AgentBase-User-Id` | Băm rồi ghi vào trace |
| `X-GreenNode-AgentBase-Request-Id` | Tương quan log |

## 11.3 Các kiểu dữ liệu cốt lõi

```python
# app/semantic/models.py
class Metric(BaseModel):
    name: str
    label_vi: str
    description_vi: str
    dataset: str
    sql: str                         # bieu thuc tong hop, KHONG phai cau SELECT day du
    unit: Literal["count","vnd","ratio","percent","days","text"]
    format: str
    higher_is_better: bool | None = None
    min_sample_size: int | None = None
    caveat_vi: str | None = None
    thresholds: dict[str, dict] | None = None
    allowed_dimensions: list[str] = Field(default_factory=list)

class Filter(BaseModel):
    dimension: str
    op: Literal["eq","ne","in","not_in","gt","gte","lt","lte","between"]
    value: Any

class MetricRequest(BaseModel):
    metrics: list[str]
    dimensions: list[str] = []
    filters: list[Filter] = []
    date_range: DateRange | None = None
    order_by: str | None = None
    order_desc: bool = True
    limit: int = 100

class CompiledQuery(BaseModel):
    query_id: str                    # hash(sql, params) - dia chi trong evidence
    sql: str
    params: dict[str, Any]
    metrics: list[Metric]
    dimensions: list[Dimension]
    caveats: list[str]
```

```python
# app/semantic/evidence.py
class Fact(BaseModel):
    fact_id: str                     # "F1"
    title: str
    query_id: str
    sql: str
    columns: list[ColumnSpec]
    rows: list[dict]                 # moi dong co khoa "_ref" = "F1.r3"
    row_count: int
    caveats: list[str]

class EvidenceSet(BaseModel):
    evidence_id: str
    generated_at: datetime
    data_version: str                # etl_run_id -> de vo hieu cache
    facts: list[Fact]
    derived: list[DerivedFact] = []
    comparisons: list[Comparison] = []

    def resolve(self, ref: str) -> Cell | None:
        """'F1.r3.romi' -> Cell(value=6.20, unit='ratio', format='0.00').
        Tra None neu khong ton tai -> lop L2 se chan."""

    def substitute(self, text: str) -> tuple[str, list[str]]:
        """Thay the moi {{ref}} bang chuoi da dinh dang.
        Tra ve (van ban, danh sach ref khong phan giai duoc)."""

    def matches_any_cell(self, value: float, policy: NumericPolicy) -> bool: ...
    def all_string_values(self) -> set[str]: ...
```

```python
# app/verify/models.py
class Severity(StrEnum): INFO="INFO"; WARN="WARN"; BLOCK="BLOCK"
class Band(StrEnum): PASS="PASS"; HEDGE="HEDGE"; ABSTAIN="ABSTAIN"; BLOCKED="BLOCKED"

class CheckResult(BaseModel):
    name: str
    passed: bool
    score: float                     # 0..1
    severity: Severity
    details: dict[str, Any] = {}
    message_vi: str | None = None

class TrustScore(BaseModel):
    value: float
    band: Band
    components: dict[str, CheckResult]
    reasons: list[str] = []
```

## 11.4 Chữ ký các module chính

### `app/agent/orchestrator.py`

```python
class Orchestrator:
    def __init__(self, catalog: Catalog, repo: Repository, llm: LLMClient,
                 prompts: PromptLoader, verifier: VerificationPipeline,
                 playbooks: PlaybookRegistry, settings: Settings): ...

    async def answer(self, question: str, *, session_id: str | None = None,
                     history: list[Turn] | None = None) -> AgentState:
        """Chay toan bo pipeline dong bo. Dung cho /invocations."""

    async def answer_stream(self, question: str, **kw) -> AsyncIterator[AgentEvent]:
        """Sinh ra AgentEvent cho SSE. Dung cho /api/chat."""

    # tung buoc - test rieng duoc
    async def _intake(self, st: AgentState) -> AgentState: ...
    async def _route(self, st: AgentState) -> AgentState: ...
    def      _select_playbook(self, st: AgentState) -> AgentState: ...
    def      _plan(self, st: AgentState) -> AgentState: ...
    async def _compute(self, st: AgentState) -> AgentState: ...
    def      _analyze(self, st: AgentState) -> AgentState: ...
    async def _narrate(self, st: AgentState) -> AgentState: ...
    async def _verify(self, st: AgentState) -> AgentState: ...
    def      _decide(self, st: AgentState) -> AgentState: ...
    def      _render(self, st: AgentState) -> AgentState: ...
    async def _trace(self, st: AgentState) -> AgentState: ...
```

Mỗi `_step` nhận `AgentState` và trả `AgentState`. Không bước nào có tác dụng phụ ngoài state và I/O đã khai báo, nên test được từng bước bằng một state dựng sẵn.

### `app/semantic/compiler.py`

```python
class QueryCompiler:
    def __init__(self, catalog: Catalog, max_rows: int = 1000): ...

    def compile(self, req: MetricRequest) -> CompiledQuery:
        """Raise UnknownMetricError / UnknownDimensionError / InvalidFilterError.
        Khong bao gio noi chuoi tu du lieu nguoi dung vao SQL."""

    def _compile_filters(self, filters, ) -> tuple[list[str], dict]: ...
    def _safe_order(self, req, metrics, dims) -> str: ...
```

### `app/data/sqlguard.py` (L0)

```python
class SQLGuard:
    ALLOWED_SCHEMAS = {"mart"}
    FORBIDDEN = {"CREATE","DROP","INSERT","UPDATE","DELETE","MERGE",
                 "ALTER","TRUNCATE","GRANT","REVOKE","COPY","CALL"}

    def __init__(self, catalog_snapshot: dict[str, set[str]]): ...

    def validate(self, sql: str) -> GuardResult:
        """1. sqlglot.parse_one -> ParseError thi chan
        2. dung 1 cau lenh, phai la exp.Select
        3. duyet AST: moi exp.Column phan giai duoc ve (bang, cot) CO THAT
           - dung sqlglot.optimizer.scope.build_scope, khong so khop chuoi
        4. moi bang thuoc schema mart
        5. co LIMIT; khong co thi chen LIMIT 500
        Tra ve GuardResult(ok, sql_rewritten, unbound_identifiers, reasons)."""

    async def explain(self, sql: str, engine) -> ExplainResult:
        """Chay EXPLAIN (khong ANALYZE) duoi role chi doc. Bat loi kieu va chi phi."""
```

Điểm quan trọng: kiểm tra chạy trên **cây cú pháp**, không phải trên chuỗi. So khớp chuỗi trên SQL bị đánh bại bởi comment, hoa thường và truy vấn lồng — một kẻ tấn công hoặc một model lú lẫn đều vượt qua được bộ lọc chuỗi.

### `app/verify/pipeline.py`

```python
class VerificationPipeline:
    def __init__(self, cfg: VerifySettings, judge: Judge | None,
                 catalog: Catalog): ...

    async def run(self, *, answer: str, evidence: EvidenceSet,
                  question: str, sql_guard: GuardResult | None = None,
                  ) -> TrustScore:
        """Chay L0..L4 dong bo (< 50ms). Neu cfg.judge_async thi dat lich L5
        chay nen va tra ve TrustScore voi judge='pending'."""

    async def run_judge_later(self, trace_id: UUID, answer: str,
                              evidence: EvidenceSet) -> JudgeResult:
        """Chay L5, cap nhat ops.agent_trace, day su kien SSE 'judge'."""
```

### `app/verify/numeric.py` (L2)

```python
TAG_RE = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")

def parse_vi_number(s: str) -> float | None:
    """'392.498.500' -> 392498500.0 ; '6,20' -> 6.2 ; '48,8%' -> 0.488
       '1,2 tỷ' -> 1200000000.0 ; tra None neu khong phai so."""

def check_numeric_grounding(text: str, ev: EvidenceSet,
                            policy: NumericPolicy) -> CheckResult: ...
```

`parse_vi_number` là hàm dễ viết sai nhất trong cả dự án, vì tiếng Việt dùng `.` làm dấu phân cách nghìn và `,` làm dấu thập phân — ngược với mặc định của Python. Nó cần một bộ test riêng với ít nhất 30 ca.

### `app/analytics/stats.py`

```python
def wilson_ci(successes: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Khoang tin cay Wilson cho ty le. Dung Wilson chu khong dung Wald vi
    Wald sai nang khi n nho hoac p gan 0/1 - dung ca hai truong hop ta co."""

def two_proportion_ztest(x1: int, n1: int, x2: int, n2: int) -> StatResult: ...

def bootstrap_mean_diff(a: Sequence[float], b: Sequence[float],
                        n_boot: int = 2000, seed: int = 42) -> StatResult:
    """Dung bootstrap thay vi t-test vi phan bo loi nhuan lech manh
    (sigma = 738k tren trung binh 200k)."""

def cohens_d(a: Sequence[float], b: Sequence[float]) -> float: ...
```

`seed=42` cố định để cùng một câu hỏi luôn cho cùng một p-value — nếu không, hai lần hỏi giống nhau có thể cho hai kết luận khác nhau về ý nghĩa thống kê, và đó là một loại bất định không ai chấp nhận được trong báo cáo.

### `app/llm/client.py`

```python
class LLMClient:
    def __init__(self, settings: LLMSettings): ...

    async def complete(self, messages: list[Message], *, model: str | None = None,
                       temperature: float | None = None, max_tokens: int | None = None,
                       response_format: Literal["text","json"] = "text",
                       ) -> Completion:
        """Bao AsyncOpenAI tro vao base_url cua MaaS.
        - Token bucket phia client (mac dinh 8 req/phut)
        - Retry co backoff mu cho 429/5xx, toi da max_retries
        - Ghi usage vao AgentState
        - Raise LLMUnavailable sau khi het luot -> orchestrator chuyen che do template"""

    async def stream(self, messages, **kw) -> AsyncIterator[str]: ...
```

Token bucket đặt ở **client**, không dựa vào việc bắt lỗi 429. Trần MaaS là 10 RPM tính chung tài khoản, nên nếu để đụng trần mới lùi thì mọi request đồng thời cùng lùi một lúc và tạo ra hiệu ứng bầy đàn.

## 11.5 Đặc tả ETL

```python
# etl/load_excel.py
COLUMN_CONTRACT: dict[str, list[str]] = {
    "fact_lead": ["lead_id","customer_id","partner_code","channel","sub_channel",
                  "create_at","product_id","campaign_id","campaign_name",
                  "utm_source","utm_medium"],
    # ... 5 bang con lai
}

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Customer_id -> customer_id, Processing_Fee -> processing_fee, ..."""

def assert_contract(table: str, df: pd.DataFrame) -> None:
    """DQ-08: thieu cot hoac thua cot -> raise. ETL dung, khong nap nua."""

def load(source: Literal["excel","parquet"], dsn: str) -> LoadReport:
    """Mot transaction: TRUNCATE ... CASCADE roi COPY lai. Idempotent."""
```

```python
# etl/dq_checks.py
CHECKS: list[Check] = [
    Check("DQ-01", Severity.WARN,  sql_disbursement_before_create),
    Check("DQ-02", Severity.WARN,  sql_nonpositive_form_time),
    Check("DQ-03", Severity.WARN,  sql_single_month_window),
    Check("DQ-08", Severity.BLOCK, py_column_contract),
    Check("INV-1", Severity.BLOCK, sql_application_id_sets_equal),
    Check("INV-2", Severity.BLOCK, sql_rejected_disbursed_disjoint),
    Check("INV-3", Severity.BLOCK, sql_counts_add_up),
    Check("INV-4", Severity.BLOCK, sql_customer_fk_complete),
    Check("INV-5", Severity.BLOCK, sql_subchannel_in_dim_campaign),
    Check("INV-6", Severity.BLOCK, sql_rejected_zero_revenue),
    Check("INV-7", Severity.BLOCK, sql_mart_rowcount_matches),
]

def run_all(dsn: str, run_id: int) -> DQReport:
    """Ghi ops.dq_result. Co BLOCK nao that bai -> exit code 1."""
```

## 11.6 Quy ước mã nguồn

| Quy ước | Chi tiết |
|---|---|
| Kiểu dữ liệu | Bắt buộc type hint ở mọi hàm public. `mypy --strict` cho `semantic/`, `verify/`, `analytics/` |
| Lỗi | Cây exception riêng trong `app/errors.py`, kế thừa `AppError`. Không `raise Exception(...)` |
| Log | `structlog`, JSON, luôn kèm `trace_id`. Không bao giờ log giá trị bí mật |
| Async | Route và LLM là async. Truy vấn DB chạy trong threadpool qua `run_in_executor` (psycopg sync) |
| Hàm thuần | `analytics/` và `verify/` không I/O — nhờ vậy test không cần DB hay mạng |
| SQL | Chỉ trong `etl/sql/*.sql` và `semantic/compiler.py`. Không rải SQL ở nơi khác |
| Tiếng Việt | Chuỗi hiển thị cho người dùng nằm trong YAML config, không hardcode trong `.py` |
| Import | `import-linter` chạy trong CI, ép các ranh giới ở [04](04-architecture.md) §4.9 |

```toml
# pyproject.toml - kiem tra ranh giới module
[[tool.importlinter.contracts]]
name = "analytics va verify phai thuan, khong I/O"
type = "forbidden"
source_modules = ["app.analytics", "app.verify"]
forbidden_modules = ["app.data", "app.llm", "app.api"]

[[tool.importlinter.contracts]]
name = "semantic khong phu thuoc llm"
type = "forbidden"
source_modules = ["app.semantic"]
forbidden_modules = ["app.llm", "app.agent"]
```

Hợp đồng thứ hai đáng giá nhất: nó khiến việc "cho LLM tự sinh định nghĩa chỉ số" trở thành lỗi CI, chứ không phải một quyết định mà ai đó có thể âm thầm đưa vào lúc 2 giờ sáng.

## 11.7 `requirements.txt`

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
pydantic==2.9.*
pydantic-settings==2.6.*
sqlalchemy==2.0.*
psycopg[binary]==3.2.*
sqlglot==25.*
openai==1.54.*
jinja2==3.1.*
pyyaml==6.0.*
pandas==2.2.*
openpyxl==3.1.*
pyarrow==17.*
scipy==1.14.*
numpy==2.1.*
cachetools==5.5.*
structlog==24.*
httpx==0.27.*
sse-starlette==2.1.*
greennode-agentbase           # theo scaffold cua AgentBase
```

Dev thêm: `pytest`, `pytest-asyncio`, `pytest-cov`, `mypy`, `ruff`, `import-linter`, `playwright`.

Cố ý **không** có `scikit-learn` ở phụ thuộc chính — k-means chỉ là chế độ đối chứng tuỳ chọn ([06](06-agent-design.md) §6.6), nên nó nằm trong nhóm `[dev]`. Không đưa một thư viện ML 100 MB vào image chỉ để phục vụ một chế độ không bao giờ dùng để trả lời người dùng.

## 11.8 Thứ tự implement

Mỗi bước dưới đây chạy được và kiểm chứng được trước khi sang bước sau.

| Bước | Việc | Chạy thử được gì |
|---|---|---|
| 1 | `etl/` + DDL + DQ | `psql` đếm ra đúng 2 687 / 1 062 / 1 625 |
| 2 | `semantic/` + `data/` | `pytest test_metrics_contract.py` khớp 6 ROMI tham chiếu |
| 3 | `api/routes_dashboard` + UI tab Chiến dịch | Dashboard chạy, **chưa cần LLM** |
| 4 | `analytics/` (stats, CLV, segmentation) + tab Chân dung + tab Hành động | Ba deliverable xong, vẫn 0 lượt LLM |
| 5 | `llm/` + `prompts/` + `agent/` + SSE chat | Chat hoạt động |
| 6 | `verify/` L2, L3, L4 | Trust badge hiện, golden set chạy |
| 7 | `verify/` L5 judge bất đồng bộ | |
| 8 | `sqlguard` + freeform SQL + self-consistency | Đường thoát mở |
| 9 | Trang admin sửa prompt/metric | Business user tự sửa được |
| 10 | Dockerfile + deploy GreenNode | |

Điểm đáng chú ý: **sau bước 4, cả ba deliverable đã xong và hoàn toàn không có hallucination**, vì chưa có LLM nào tham gia. LLM được thêm vào ở bước 5 để làm phần diễn giải và hỏi đáp tự do. Nếu hết thời gian hackathon ở bước 4, vẫn có sản phẩm chạy được để demo — đây là một thứ tự được chọn để giảm rủi ro, không phải ngẫu nhiên.
