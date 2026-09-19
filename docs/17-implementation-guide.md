# 17 — Hướng dẫn triển khai

> **Tài liệu này dành cho người (hoặc agent) viết code.** Nó giả định bạn chưa đọc gì khác. Mọi nhiệm vụ đều có tiêu chí nghiệm thu **kiểm chứng được bằng một lệnh**, không phải bằng cảm nhận.

## 17.1 Đọc gì trước khi gõ dòng code đầu tiên

Đọc theo thứ tự này, không bỏ qua:

| # | File | Vì sao bắt buộc |
|---|---|---|
| 1 | [01-overview.md](01-overview.md) §1.5 | Bảy nguyên tắc. Mọi quyết định code phải tuân theo |
| 2 | [02-data-model.md](02-data-model.md) §2.1, §2.4 | Ba cấu trúc bất thường của dữ liệu và bốn cái bẫy |
| 3 | [`app/contracts.py`](../app/contracts.py) | Hợp đồng giữa các module. Đây là đặc tả ở mức class/function |
| 4 | [04-architecture.md](04-architecture.md) §4.9 | Ranh giới module — CI ép chúng |
| 5 | Nhiệm vụ của bạn trong §17.4 dưới đây | |

Ba điều về dữ liệu mà nếu không biết thì code sẽ sai âm thầm:

1. **`fact_loan` không có `campaign_id` và không có `lead_id`.** Cầu nối duy nhất là `sub_channel`.
2. **1 062 hồ sơ bị từ chối có `loan_amount`, `tenure`, `rate`, `balance` đều NULL.** Đúng về nghiệp vụ. `SUM(loan_amount)/COUNT(*)` sai 39%.
3. **Lợi nhuận lệch cực mạnh:** trung bình +199 629, trung vị −86 175, 53,8% khách lỗ.

## 17.2 Đã có sẵn những gì

Tất cả các file dưới đây **đã viết xong và đã kiểm chứng**. Không viết lại, không "cải tiến" — chúng là nguồn sự thật.

| Nhóm | File | Trạng thái |
|---|---|---|
| Hợp đồng interface | `app/contracts.py` | 14 Protocol, 52 kiểu dữ liệu |
| Bảng mã lỗi | `app/errors.py` | 40 mã, có `describe_catalog()` |
| Catalog chỉ số | `config/semantic/metrics.yml` | **53 chỉ số, 42 có giá trị tham chiếu đã kiểm chứng** |
| Dataset & dimension | `config/semantic/entities.yml` | 4 dataset, 25 dimension |
| Phân khúc, CLV, hành động | `config/analytics.yaml` | 8 luật, bảng tra `p_repeat`, 6 hành động |
| Ngưỡng kiểm chứng | `config/verify.yaml` | 7 lớp, 24 marker so sánh, 15 marker nhân quả |
| Thông báo streaming | `config/stages.yaml` | 9 giai đoạn, override theo 9 playbook |
| Cấu hình môi trường | `config/app.yaml`, `config/profiles/*.yaml` | local / greennode / test |
| Playbook | `config/playbooks/*.yml` | 9 file |
| Prompt | `prompts/*.yaml` | 9 file, **36 few-shot dùng số thật** |
| DDL | `etl/sql/0{0,1,2,3}_*.sql` | Đã chạy kiểm chứng trên DuckDB: 12/12 bất biến đạt |
| Golden set | `evals/golden/qa_set.yaml` | **100 ca, 37 ca bẫy** |

Việc của bạn là viết **code Python**, không phải viết lại cấu hình.

## 17.3 Năm quy tắc không được phá

Vi phạm bất kỳ quy tắc nào dưới đây là lỗi nghiêm trọng, kể cả khi test vẫn xanh.

| # | Quy tắc | Vì sao |
|---|---|---|
| R1 | **LLM không bao giờ tự tính một con số.** Mọi con số đến từ SQL đã chạy | Nguyên tắc P1. Toàn bộ thiết kế chống hallucination dựa trên đây |
| R2 | **Không bao giờ nối chuỗi dữ liệu người dùng vào SQL.** Luôn bind parameter | SQL injection + lỗi kiểu |
| R3 | **`analytics/` và `verify/` không được import `data`, `llm`, `api`** | Giữ chúng thuần để test không cần DB/mạng. `import-linter` ép trong CI |
| R4 | **Không hạ ngưỡng kiểm chứng để test xanh.** Sửa code, đừng sửa rào | Rào tự nới là rào không tồn tại |
| R5 | **Không hardcode chuỗi hiển thị tiếng Việt trong `.py`.** Chúng nằm trong YAML | Nguyên tắc P4: nội dung là cấu hình |

Khi phân vân giữa "làm cho chạy" và "làm cho đúng", chọn đúng rồi báo lại chỗ vướng.

## 17.4 Danh sách nhiệm vụ

Mỗi nhiệm vụ có **Xong khi** kiểm chứng được bằng lệnh. Chạy lệnh đó trước khi coi là xong.

---

### T01 — Dựng dự án và kết nối DB

**Tạo:** `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `.dockerignore`, `docker-compose.dev.yml`, `app/__init__.py`, `app/settings.py`, `app/logging_.py`

`app/settings.py` theo [10-config-secrets.md](10-config-secrets.md) §10.6: nạp `app.yaml` → `profiles/{APP_PROFILE}.yaml` → `secrets.yaml` → biến môi trường; giải quyết `*_from_secret` và `*_from_env`.

**Xong khi:**
```bash
docker compose -f docker-compose.dev.yml up -d
python -c "from app.settings import get_settings; s=get_settings(); print(s.profile, s.app.port)"
# -> "test 8080"  (voi APP_PROFILE=test)
```

---

### T02 — ETL và DDL

**Tạo:** `etl/__init__.py`, `etl/load_excel.py`, `etl/build_marts.py`, `etl/dq_checks.py`

`load_excel.py` phải: chuẩn hoá tên cột về snake_case, **assert** danh sách cột khớp `COLUMN_CONTRACT` (DQ-08), ép kiểu, nạp trong một transaction, idempotent.

`dq_checks.py` chạy DQ-01…09 và INV-1…7 từ [02-data-model.md](02-data-model.md) §2.5, ghi `ops.dq_result`, **exit code 1** nếu có mục `BLOCK` fail.

**Xong khi:**
```bash
python -m etl.load_excel --source excel && python -m etl.build_marts && python -m etl.dq_checks
psql "$TEST_URL" -c "SELECT COUNT(*) FROM mart.mart_application"          # 2687
psql "$TEST_URL" -c "SELECT COUNT(*) FROM mart.v_customer_segment WHERE segment='_unclassified'"  # 0
pytest tests/test_etl_invariants.py -q                                    # 12 passed
```

---

### T03 — Semantic layer

**Tạo:** `app/semantic/{__init__,models,catalog,compiler,evidence}.py`

`compiler.py` phải giữ **năm bất biến** ở [05-semantic-layer.md](05-semantic-layer.md) §5.3. `evidence.py` hiện thực `EvidenceSet.resolve/substitute/matches_any_cell/all_string_values` theo `app/contracts.py`.

**Xong khi:**
```bash
pytest tests/test_semantic_compiler.py tests/test_metrics_contract.py -q
# test_metrics_contract phai khang dinh 6 gia tri ROMI:
#   CMP-ZL-RL1 6.20 | CMP-GG-001 1.60 | CMP-FB-001 1.31
#   CMP-TT-001 0.67 | CMP-PTN-MOMO -0.41 | CMP-PTN-BRK01 -1.85
```

Viết `test_metrics_contract.py` bằng cách **đọc trường `reference` trong `metrics.yml`** — 42 chỉ số đã có sẵn giá trị đối chứng, không cần gõ tay.

---

### T04 — Tầng truy cập dữ liệu

**Tạo:** `app/data/{__init__,engines,repository,cache}.py`

Ba engine tách biệt theo role ([03-database-choice.md](03-database-choice.md) §3.3). `engines.py` phải có `assert_read_only_role()`: thử `INSERT` bằng `mkt_agent_ro` và **kỳ vọng nhận lỗi**.

**Xong khi:**
```bash
pytest tests/test_engines.py -q
# test_agent_role_cannot_write phai PASS (nghia la INSERT bi tu choi)
```

---

### T05 — Thống kê, CLV, phân khúc

**Tạo:** `app/analytics/{__init__,stats,clv,segmentation,funnel,derive}.py`

Hàm thuần, không I/O. `bootstrap_mean_diff` dùng `seed=42` cố định.

`clv.py` dùng bảng tra `p_repeat` theo **hồ sơ hành vi** `(income_band × has_app)` trong `config/analytics.yaml`, **không** dùng tỷ lệ trong phân khúc giá trị — xem cảnh báo ở [06-agent-design.md](06-agent-design.md) §6.5.

**Xong khi:**
```bash
pytest tests/test_stats.py tests/test_clv.py tests/test_segmentation.py -q
# Cac khang dinh bat buoc:
#   wilson_ci(103, 284) ~ (0.309, 0.420)
#   ANOVA 7 nhom nghe -> p = 0.9718, significant = False
#   estimate_clv(n=29) -> insufficient = True
#   segmentation: tong = 2901, _unclassified = 0, high_risk = 97
lint-imports    # analytics khong duoc import data/llm/api
```

---

### T06 — API dashboard và UI (chưa cần LLM)

**Tạo:** `app/api/{app_factory,deps,schemas,routes_health,routes_dashboard,routes_segments,routes_actions}.py`, `app/web/formatting.py`, `app/web/templates/*`, `app/web/static/*`, `main.py`, `Dockerfile`

`/health` **không chạm DB**. `/readyz` kiểm tra DB + `ops.v_blocking_dq` + catalog.

**Xong khi:**
```bash
python main.py &
curl -s localhost:8080/health   | jq -e '.status=="ok"'
curl -s localhost:8080/readyz   | jq -e '.db=="ok"'
curl -s localhost:8080/api/dashboard/campaigns | jq '.[] | select(.campaign_id=="CMP-PTN-BRK01") | .romi'   # -1.85
pytest tests/test_formatting.py -q     # fmt_vnd(392498488) == "392.498.488 VND" ... xem 09 muc 9.8
playwright test tests/e2e/test_ui_chat_height.py     # chat <= 60vh o 3 viewport
```

**Tới đây, ba deliverable D1/D2/D3 đã chạy được mà chưa có LLM nào tham gia.** Đây là cột mốc an toàn — nếu hết thời gian, vẫn có sản phẩm demo được và không thể hallucinate.

---

### T07 — LLM client và prompt loader

**Tạo:** `app/llm/{client,mock,usage}.py`, `app/prompts/loader.py`

Token bucket đặt ở **client** (mặc định 8 req/phút), không dựa vào bắt lỗi 429.

`PromptLoader` render Jinja2 **chỉ cho `system` và `instructions`**; `few_shots` chèn nguyên văn — nếu không, các thẻ `{{F1.r1.romi}}` trong ví dụ sẽ bị Jinja nuốt mất.

**Xong khi:**
```bash
pytest tests/test_prompt_loader.py tests/test_llm_client.py -q
# Khang dinh bat buoc:
#   loader.validate_all() -> khong loi tren ca 9 file
#   few_shot giu nguyen chuoi "{{F1.r1.romi}}"
#   YAML hong -> GIU NGUYEN ban dang chay, khong raise
#   rate limit: 20 request dong thoi -> khong request nao vuot 8/phut
```

---

### T08 — Agent orchestrator

**Tạo:** `app/agent/{state,orchestrator,router,planner,narrator,decider,renderer,playbooks,stages}.py`, `app/agent/tools/*.py`

Mỗi bước là `step(state) -> state`. Router thử luật regex trước khi gọi LLM.

**Xong khi:**
```bash
pytest tests/test_orchestrator.py -q
APP_PROFILE=test python -c "
import asyncio; from app.agent.orchestrator import Orchestrator
st = asyncio.run(build().answer('Chiến dịch nào đang lỗ?'))
assert st.llm_calls <= 2, st.llm_calls
assert 'Broker' in st.narrative_final
print(st.decision, st.trust.value)"
```

---

### T09 — Kiểm chứng L2, L3, L4

**Tạo:** `app/verify/{models,pipeline,numeric,entity,stats_guard,vi_text}.py`

`parse_vi_number` là hàm dễ sai nhất trong dự án: tiếng Việt dùng `.` cho hàng nghìn và `,` cho thập phân — ngược với mặc định Python. Cần ≥30 ca test, gồm cả ca ngược (`CMP-FB-001` **không** phải số).

**Xong khi:**
```bash
pytest tests/test_vi_number_parser.py -q      # >= 30 ca
pytest tests/test_numeric_grounding.py tests/test_entity_grounding.py tests/test_stats_guard.py -q
# Khang dinh bat buoc:
#   text co so tran khong khop -> passed = False, severity = BLOCK
#   the {{F9.r1.romi}} khong ton tai -> passed = False
#   "48,8%" khop cell 0.488 (alias ratio_x100)
#   "1,2 tỷ" khop 1_200_000_000
#   cau "Freelancer sinh lời nhất" voi significant=False -> BLOCK
python -m evals.run_eval --split dev --profile test
# numeric_grounding_rate == 1.000  <- CONG CUNG, khong bao gio duoc thap hon
```

---

### T10 — Streaming

**Tạo:** `app/agent/streaming.py`, `app/api/routes_chat.py`, `app/web/static/chat.js`

`StreamingVerifier` theo [15-streaming.md](15-streaming.md) §15.4: gom token thành khối, thay thế thẻ, kiểm chứng, rồi mới phát.

**Xong khi:**
```bash
pytest tests/test_streaming.py -q
# Khang dinh bat buoc:
#   test_streaming_never_leaks_tags: 500 chuoi token cat the o moi vi tri
#       -> KHONG block.md nao chua "{{" hoac "}}"
#   test_invocations_matches_stream: answer() va answer_stream() ghep lai
#       -> CUNG MOT markdown
#   test_progress_monotonic: progress khong giam, ket thuc o 1.0
curl -N -X POST localhost:8080/api/chat -H 'Accept: text/event-stream' \
     -d '{"message":"Tạo dashboard"}' | head -20
# -> phai thay: event: stage voi label "Đang tạo dashboard hiệu quả chiến dịch"
```

---

### T11 — LLM judge và Trust Score

**Tạo:** `app/verify/judge.py`, `app/verify/consistency.py`, `app/telemetry/{trace,store}.py`

Judge chạy **bất đồng bộ**, không chặn đường găng.

**Xong khi:**
```bash
pytest tests/test_judge.py tests/test_trust_score.py -q
# hard_fail -> trust = 0.0 bat ke cac diem khac
# judge tra ve sau `done`, cap nhat ops.agent_trace
psql "$TEST_URL" -c "SELECT prompt_version, model_name, profile FROM ops.agent_trace LIMIT 1"
# -> ba cot KHONG duoc NULL
```

---

### T12 — SQL guard và đường freeform

**Tạo:** `app/data/sqlguard.py`, `app/agent/tools/sql_tool.py`

Kiểm tra trên **cây cú pháp** bằng `sqlglot`, không so khớp chuỗi.

**Xong khi:**
```bash
pytest tests/test_sqlguard.py -q       # >= 25 ca
# Khang dinh bat buoc:
#   "DROP TABLE x" -> chan
#   "SELECT * FROM mart.mart_application /* hidden */ ; DROP TABLE y" -> chan
#   "SELECT fake_col FROM mart.mart_application" -> SQLUnboundIdentifier
#   "SELECT * FROM raw.fact_loan" -> SQLSchemaNotAllowed
#   "SELECT campaign_id FROM mart.mart_application" -> tu chen LIMIT 500
```

---

### T13 — Trang admin

**Tạo:** `app/api/routes_admin.py`, `app/web/templates/admin/*.html`

`/api/admin/*` không có `X-Admin-Token` đúng thì trả **404**, không phải 401.

**Xong khi:**
```bash
curl -s -o /dev/null -w '%{http_code}' localhost:8080/api/admin/prompts          # 404
curl -s -H "X-Admin-Token: $T" localhost:8080/api/admin/prompts | jq 'length'    # 9
# Sua mot prompt qua UI -> reload < 5s, ghi ops.prompt_history
```

---

### T14 — Đóng gói và deploy

**Tạo:** `.greennode.json`, `.env.example`, `scripts/deploy_greennode.ps1`

**Xong khi:**
```bash
docker build --platform linux/amd64 -t mkt-insight-agent:v1.0.0 .
docker run -p 8080:8080 --env-file .env mkt-insight-agent:v1.0.0
curl -s localhost:8080/health   # 200
# Theo tiep docs/12-build-deploy.md muc 12.7
```

---

## 17.5 Thứ tự và cách chia việc

```
T01 ─┬─> T02 ──> T03 ──> T04 ──> T06 ──> T07 ──> T08 ──> T10 ──> T13 ──> T14
     │                                     │
     └─────────> T05 ───────────────────────> T09 ──> T11
                                              │
                                              └─> T12
```

Với ba người:

| Người | Nhiệm vụ | Bắt đầu được khi nào |
|---|---|---|
| A | T01 → T02 → T03 → T04 | Ngay |
| B | T05 → T09 → T11 → T12 | **Ngay** — chỉ cần `app/contracts.py`, không cần DB, không cần LLM |
| C | T06 → T07 → T10 → T13 | Sau khi A xong T03 (cần `EvidenceSet`) |

Người B khởi động được ngay lập tức không phải may mắn — đó là lý do `analytics` và `verify` bị cấm import `data` và `llm` ngay từ đầu.

## 17.6 Cổng kiểm tra trước mỗi lần commit

```bash
ruff check . && mypy app/semantic app/verify app/analytics && lint-imports
pytest tests/ -q --cov=app --cov-fail-under=75
python -m evals.run_eval --split dev --profile test --fail-on-regression
```

Ba cổng **cứng**, không có ngoại lệ:

* `numeric_grounding_rate` phải bằng **1,000**
* `must_not_mention_violations` phải bằng **0**
* Không có mục DQ mức `BLOCK` nào fail

## 17.7 Khi bị vướng

| Tình huống | Làm gì |
|---|---|
| Chỉ số trong `metrics.yml` cho kết quả khác `reference` | **Dừng lại.** Hoặc ETL sai, hoặc compiler sai. Không sửa `reference` |
| Model viết chữ số thay vì thẻ | Theo thứ tự: thêm few-shot phản ví dụ → hạ `temperature` xuống 0,1 → đổi model lớn hơn. **Không tắt L2** |
| Test đỏ vì ngưỡng kiểm chứng | Sửa code. Không hạ ngưỡng |
| Câu hỏi thường rơi xuống `freeform` | Đó là tín hiệu **thiếu chỉ số** trong catalog, không phải cần nới rào ở `freeform` |
| Thiếu thông tin trong tài liệu | Ghi lại giả định trong code bằng comment `# ASSUMPTION:` rồi báo lại. Đừng im lặng đoán |
| Đụng trần 10 RPM khi dev | Dùng `APP_PROFILE=test` (provider mock) cho mọi test |

## 17.8 Định nghĩa "xong" cho cả dự án

```bash
# 1. Du lieu
python -m etl.load_excel --source excel && python -m etl.build_marts && python -m etl.dq_checks

# 2. Chat luong code
ruff check . && mypy app/semantic app/verify app/analytics && lint-imports
pytest tests/ -q --cov=app --cov-fail-under=75

# 3. Chat luong cau tra loi
python -m evals.run_eval --split all --seeds 3 --report html
#   execution_accuracy        >= 0.90
#   numeric_grounding_rate    == 1.000
#   refusal_accuracy          >= 0.85
#   false_refusal_rate        <= 0.10
#   must_not_mention_violations == 0

# 4. Giao dien
playwright test tests/e2e/

# 5. Deploy
docker build --platform linux/amd64 -t mkt-insight-agent:v1.0.0 . && docker push ...
curl -s "$ENDPOINT/readyz" | jq -e '.db=="ok" and .dq=="ok"'
curl -s "$ENDPOINT/api/dashboard/campaigns" | jq '.[] | select(.campaign_id=="CMP-ZL-RL1") | .romi'   # 6.20
```

Điểm nghiệm thu cuối cùng và đắt giá nhất: hỏi agent **"Nhóm nghề nghiệp nào sinh lời nhất?"** trên môi trường prod. Câu trả lời đúng là nói rằng chênh lệch nằm trong sai số thống kê — không phải gọi tên một nhóm.
