# 10 — Cấu hình, model theo môi trường, và bí mật

> Yêu cầu gốc: *"Local và prod (greennode) sẽ sử dụng model khác nhau, do đó cần nơi config"* và *"Tạm thời model và API key lưu trong repo."*

## 10.1 Nguyên tắc: một codebase, nhiều profile

Không có `if os.environ["ENV"] == "prod"` ở bất cứ đâu trong code nghiệp vụ. Khác biệt giữa môi trường **chỉ** thể hiện ở file profile.

```
config/
  app.yaml                 # mac dinh dung chung
  profiles/
    local.yaml             # may dev
    greennode.yaml         # AgentBase Runtime
    test.yaml              # CI, tro vao Postgres trong docker-compose
  secrets.yaml             # KHONG commit sau hackathon; xem 10.5
  secrets.example.yaml     # mau, co commit
  semantic/metrics.yml
  semantic/entities.yml
  playbooks/*.yml
  verify.yaml
  analytics.yaml
```

Chọn profile bằng đúng một biến môi trường:

```bash
APP_PROFILE=local       # mac dinh khi khong dat
APP_PROFILE=greennode   # dat trong environmentVariables cua Agent Runtime
APP_PROFILE=test        # CI
```

## 10.2 Thứ tự ưu tiên khi nạp cấu hình

```
1. config/app.yaml                    (nen)
2. config/profiles/{APP_PROFILE}.yaml (ghi de theo moi truong)
3. config/secrets.yaml                (bi mat)
4. Bien moi truong                    (uu tien cao nhat)
```

Biến môi trường thắng tất cả, vì đó là cơ chế duy nhất AgentBase Runtime cung cấp để truyền cấu hình vào container (`environmentVariables` lúc tạo/cập nhật runtime). Nhờ vậy ta đổi model trên prod mà không cần build lại image.

Quy tắc đặt tên biến: `MKT_` + đường dẫn khoá viết hoa, phân cách bằng `__`.

```bash
MKT_LLM__MODEL=...            # ghi de llm.model
MKT_DATABASE__URL=...         # ghi de database.url
MKT_VERIFY__T_HIGH=0.88       # ghi de verify.t_high
```

## 10.3 Nội dung các file

### `config/app.yaml` — mặc định dùng chung

```yaml
app:
  name: "Marketing Insight Agent"
  locale: "vi"
  timezone: "Asia/Ho_Chi_Minh"
  port: 8080                 # AgentBase BAT BUOC cong nay

database:
  pool_size: 5
  max_overflow: 5
  statement_timeout_ms: 15000
  schema_read: "mart"

llm:
  provider: "openai_compatible"
  timeout_s: 60
  max_retries: 3
  retry_backoff_s: 2
  rate_limit:
    requests_per_minute: 8   # thap hon tran 10 RPM cua MaaS
    burst: 3

agent:
  max_llm_calls_per_question: 2
  enable_freeform_sql: true
  self_consistency_k: 3       # chi ap dung cho duong freeform
  max_repair_attempts: 3
  answer_cache_ttl_s: 900

verify:
  weights: { schema: 0.15, numeric: 0.25, entity: 0.10,
             stats: 0.20, judge: 0.20, consistency: 0.10 }
  t_high: 0.85                # HIEU CHINH tren golden set truoc khi tin
  t_low: 0.60
  alpha: 0.05
  min_effect_size: 0.2
  min_sample_size: 30
  judge_async: true

analytics:
  horizon_factor: 1.0         # gia dinh CLV, xem tai lieu 06 muc 6.5
  profit_percentile_high: 0.75

ui:
  chat_max_viewport_ratio: 0.60   # rang buoc 60% man hinh
  max_answer_words: 400
```

### `config/profiles/local.yaml`

```yaml
llm:
  base_url: "http://localhost:11434/v1"    # Ollama tren may dev
  model: "qwen2.5:14b-instruct"
  judge_model: "qwen2.5:7b-instruct"       # judge dung model nho hon
  temperature: 0.2
  rate_limit:
    requests_per_minute: 60                # local khong bi tran MaaS
    burst: 10

database:
  # TRO TOI CUNG MOT vDB RDS tren GreenNode (yeu cau: dung chung 1 DB)
  url_from_secret: "database.url"

agent:
  enable_freeform_sql: true

logging:
  level: "DEBUG"
  sql_echo: true
```

### `config/profiles/greennode.yaml`

```yaml
llm:
  base_url: "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
  model_from_env: "LLM_MODEL"          # doc tu environmentVariables cua Runtime
  model_fallback: "<dien ma model da ENABLED>"   # xem 10.4
  judge_model_from_env: "LLM_JUDGE_MODEL"
  api_key_from_env: "LLM_API_KEY"
  temperature: 0.2
  rate_limit:
    requests_per_minute: 8             # tran tai khoan la 10 RPM
    burst: 2

database:
  url_from_secret: "database.url"      # CUNG mot instance voi local
  pool_size: 3                          # flavor 1x1-general, tiet kiem ket noi

agent:
  enable_freeform_sql: true
  self_consistency_k: 1                # tiet kiem quota; tat self-consistency

verify:
  judge_async: true                    # bat buoc o prod

logging:
  level: "INFO"
  sql_echo: false
```

### `config/profiles/test.yaml`

```yaml
llm:
  provider: "mock"                     # tra ve cau tra loi co dinh, 0 goi mang
  model: "mock-narrator"
database:
  url: "postgresql+psycopg://mkt_owner:devonly@localhost:55432/mkt_insight"
agent:
  enable_freeform_sql: true
verify:
  judge_async: false                   # test can ket qua dong bo
```

Provider `mock` là thứ làm golden set chạy được trong CI mà không tốn quota MaaS và không phụ thuộc mạng. Nó đọc câu trả lời mẫu từ `tests/fixtures/mock_responses/`.

## 10.4 Chọn model — một cảnh báo cần đọc trước khi code

Sổ tay BTC gợi ý ba model: **MiniMax M2.5**, **Qwen 3.5 27B**, **Gemma 4 31B-IT**.

Đối chiếu với catalog chính thức của GreenNode MaaS:

| Model trong sổ tay | Trạng thái trong catalog |
|---|---|
| MiniMax M2.5 | ✅ Có (chỉ text) |
| Gemma 4 31B-IT | ✅ Có (text + ảnh) |
| **Qwen 3.5 27B** | ❌ **Không thấy trong catalog.** Các bản Qwen được liệt kê là Qwen 3.7 Plus, Qwen 3.6 Plus, Qwen 3.6 Flash |

**Vì vậy không hardcode tên model theo sổ tay.** Trước khi viết code, liệt kê model thật sự đang bật cho tài khoản và lấy đúng mã định danh:

```bash
# dung script trong greennode-agentbase-skills
./.claude/skills/agentbase/scripts/aip.sh models list --status ENABLED
```

Mã lấy từ trường `code`/`name` của API mới là thứ điền vào `LLM_MODEL`; bảng trong tài liệu chỉ hiện tên hiển thị.

Hai điều nữa cần biết về MaaS:

* API key phải ở trạng thái **ACTIVE** mới dùng được. Key mới tạo ở trạng thái `CREATING` — phải chờ.
* Model phải được **enable** riêng cho tài khoản (`aip.sh models enable <uuid>`).

### Gợi ý chọn model theo vai trò

| Vai trò | Yêu cầu | Gợi ý |
|---|---|---|
| **Narrator** | Viết tiếng Việt tốt, tuân thủ ràng buộc định dạng chặt (bắt buộc dùng thẻ thay cho số) | Model lớn nhất đang ENABLED |
| **Router** | Phân loại ngắn, trả JSON | Model nhỏ/nhanh |
| **Judge** | Theo chỉ dẫn, `temperature=0`, output ngắn | Model nhỏ — chấm điểm không cần model to |

Vì trần 10 RPM tính chung cả tài khoản, dùng model nhỏ cho router và judge **không** giúp tăng số request, nhưng giúp giảm độ trễ và chi phí token.

Nếu narrator không tuân thủ được quy tắc "không viết chữ số" một cách ổn định, đừng nới quy tắc — hãy làm ba việc theo thứ tự: (1) thêm few-shot phản ví dụ, (2) hạ `temperature` xuống 0,1, (3) đổi sang model lớn hơn. Tuyệt đối không tắt lớp L2 để "cho nó chạy".

## 10.5 Bí mật

Theo yêu cầu, bí mật tạm thời nằm trong repo. Thiết kế sao cho việc đó an toàn nhất có thể và **gỡ ra được chỉ bằng một thay đổi**.

### `config/secrets.example.yaml` — file này có commit

```yaml
database:
  url: "postgresql+psycopg://mkt_agent_ro:CHANGEME@<rds-host>:5432/mkt_insight?sslmode=require"
  url_admin: "postgresql+psycopg://mkt_owner:CHANGEME@<rds-host>:5432/mkt_insight?sslmode=require"
  url_trace: "postgresql+psycopg://mkt_trace_rw:CHANGEME@<rds-host>:5432/mkt_insight?sslmode=require"

llm:
  api_key: "CHANGEME"

greennode:
  client_id: "CHANGEME"        # KHONG can khi chay tren AgentBase - platform tu tiem
  client_secret: "CHANGEME"

admin:
  token: "CHANGEME"
```

### Quy tắc phải giữ

1. **Repo để private.** Toàn bộ thiết kế này giả định như vậy.
2. **Duy nhất một file chứa bí mật:** `config/secrets.yaml`. Không rải key ra nhiều nơi.
3. **Duy nhất một lớp đọc bí mật:** `app/settings.py`. Không nơi nào khác gọi `os.environ` để lấy key.
4. **Agent dùng role chỉ đọc.** Kể cả bị lộ `database.url`, kẻ tấn công không sửa/xoá được gì ([03](03-database-choice.md) §3.3).
5. **Đổi toàn bộ key ngay sau hackathon**, và xoá instance vDB.
6. **Không bao giờ log bí mật.** Logger có filter che chuỗi trùng với giá trị bí mật.

### Khi chuyển sang chế độ an toàn, chỉ cần đổi một chỗ

```python
# app/settings.py -- diem duy nhat can sua
def load_secrets(profile: str) -> Secrets:
    if os.getenv("MKT_SECRETS_BACKEND") == "agentbase_identity":
        # AgentBase Access Control: lay key qua agent identity
        return Secrets.from_identity_client()
    if os.getenv("MKT_SECRETS_BACKEND") == "env":
        return Secrets.from_env()
    return Secrets.from_yaml(Path("config/secrets.yaml"))   # mac dinh PoC
```

Tài liệu GreenNode nói rõ: trường `environmentVariables` của Runtime là dành cho **cấu hình không nhạy cảm**, còn bí mật thật nên đặt ở **Access Control** (auth config của agent identity) và lấy ra lúc chạy. Đây là đường đi khi dự án qua khỏi giai đoạn PoC, và nhánh `agentbase_identity` ở trên chừa sẵn chỗ cho nó.

### `.gitignore`

```gitignore
config/secrets.yaml      # BO COMMENT dong nay ngay khi het hackathon
.env
*.pem
__pycache__/
.venv/
data/exports/
```

## 10.6 Lớp Settings

```python
# app/settings.py
class LLMSettings(BaseModel):
    provider: Literal["openai_compatible", "mock"]
    base_url: str
    model: str
    judge_model: str | None = None
    api_key: SecretStr
    temperature: float = 0.2
    timeout_s: int = 60
    max_retries: int = 3
    requests_per_minute: int = 8

class Settings(BaseSettings):
    profile: str = Field("local", alias="APP_PROFILE")
    app: AppSettings
    database: DatabaseSettings
    llm: LLMSettings
    agent: AgentSettings
    verify: VerifySettings
    analytics: AnalyticsSettings
    ui: UISettings

    model_config = SettingsConfigDict(env_prefix="MKT_", env_nested_delimiter="__")

@lru_cache
def get_settings() -> Settings:
    profile = os.getenv("APP_PROFILE", "local")
    raw = deep_merge(
        yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8")),
        yaml.safe_load(Path(f"config/profiles/{profile}.yaml").read_text(encoding="utf-8")),
    )
    raw = resolve_secret_refs(raw, load_secrets(profile))   # xu ly *_from_secret
    raw = resolve_env_refs(raw)                             # xu ly *_from_env
    return Settings(**raw)
```

### Fail-fast lúc khởi động

Ứng dụng tự kiểm tra ngay trong `lifespan` và **từ chối khởi động** nếu có vấn đề. Phát hiện cấu hình sai lúc boot rẻ hơn nhiều so với phát hiện giữa buổi demo:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    assert s.llm.api_key.get_secret_value() not in ("", "CHANGEME"), "Chua dat LLM api_key"
    assert s.app.port == 8080, "AgentBase bat buoc cong 8080"
    await check_db_connectivity(s)                 # ket noi + SELECT 1
    await assert_read_only_role(s)                 # thu INSERT -> phai bi tu choi
    catalog = load_catalog()                       # metrics.yml phai parse duoc
    validate_catalog_against_db(catalog, s)        # moi cot trong metrics.yml phai co that
    prompts = PromptLoader(Path("prompts")).validate_all()
    log.info("ready", profile=s.profile, model=s.llm.model,
             metrics_version=catalog.version, prompt_count=len(prompts))
    yield
```

`assert_read_only_role` đáng giá từng dòng: nó thử chạy một câu `INSERT` bằng `engine_ro` và **kỳ vọng nhận lỗi**. Nếu câu lệnh đó thành công, nghĩa là ai đó đã cấu hình nhầm connection string admin cho agent — và ứng dụng dừng ngay thay vì chạy với một rào chắn đã hỏng.

## 10.7 Biến môi trường cần đặt trên Agent Runtime

```json
{
  "APP_PROFILE": "greennode",
  "LLM_MODEL": "<ma model da ENABLED>",
  "LLM_JUDGE_MODEL": "<ma model nho>",
  "LLM_BASE_URL": "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1",
  "LLM_API_KEY": "<api key MaaS o trang thai ACTIVE>",
  "MKT_DATABASE__URL": "postgresql+psycopg://mkt_agent_ro:...@<rds-host>:5432/mkt_insight?sslmode=require",
  "MKT_ADMIN__TOKEN": "<random>",
  "LOG_LEVEL": "info"
}
```

**Không** đặt `GREENNODE_CLIENT_ID`, `GREENNODE_CLIENT_SECRET`, `GREENNODE_AGENT_IDENTITY`, `GREENNODE_ENDPOINT_URL` — nền tảng tự tiêm bốn biến này. Đặt tay sẽ ghi đè lên giá trị đúng.

Lưu ý thực tế: portal ghi rõ `environmentVariables` là "non-sensitive config only". Đặt `LLM_API_KEY` và mật khẩu DB ở đây là một lối tắt có ý thức cho PoC, đồng bộ với yêu cầu "tạm lưu key trong repo". Đường đi đúng khi lên dữ liệu thật đã mô tả ở §10.5.
