# Marketing Insight Agent — Bộ tài liệu thiết kế

> **Dự án:** MSB x GreenNode AI Hackathon 2026 — Agent phân tích hiệu quả chiến dịch & giá trị vòng đời khách hàng
> **Trạng thái:** Design v1.0 — PoC
> **Ngày:** 2026-09-19

## 1. Agent này làm gì

Đọc dữ liệu chiến dịch marketing + hồ sơ vay + P&L từ database, tự phân tích và trả lời 3 câu hỏi nghiệp vụ:

| # | Deliverable | Câu hỏi nghiệp vụ | Người dùng chính |
|---|---|---|---|
| D1 | **Dashboard hiệu quả từng chiến dịch** | Chiến dịch nào đang lãi/lỗ? Phễu rơi ở đâu? Tiền marketing nên dồn vào đâu? | Digital Marketing Lead |
| D2 | **Chân dung tập KH tiềm năng** | Tập khách nào đáng theo đuổi? Họ trông như thế nào? Vì sao? | CRM / Segment Manager |
| D3 | **Hành động nâng cao CLV** | Làm gì, với ai, kỳ vọng thu về bao nhiêu? | Head of Retail Lending |

Toàn bộ kết luận **bắt buộc truy vết được xuống dòng dữ liệu gốc** — đây là ràng buộc thiết kế số một, không phải tính năng phụ.

## 2. Thứ tự đọc

| File | Nội dung | Đọc nếu bạn là |
|---|---|---|
| [01-overview.md](01-overview.md) | Bối cảnh, phạm vi, non-goals, nguyên tắc thiết kế | Mọi người — **đọc đầu tiên** |
| [02-data-model.md](02-data-model.md) | Profiling dữ liệu thật, star schema, DDL, ETL, data quality | Data engineer |
| [03-database-choice.md](03-database-choice.md) | Chọn DB nào, cài ở đâu trên GreenNode, vì sao | DevOps / Data |
| [04-architecture.md](04-architecture.md) | Kiến trúc tổng thể C4, tech stack, luồng xử lý | Tech lead |
| [05-semantic-layer.md](05-semantic-layer.md) | Metric catalog — trái tim chống hallucination | Data + BE |
| [06-agent-design.md](06-agent-design.md) | Agent graph, tools, state, 3 playbooks | AI engineer |
| [07-prompt-fewshot.md](07-prompt-fewshot.md) | Cách sửa nội dung phân tích mà không đụng code | **Business user + AI eng** |
| [08-anti-hallucination.md](08-anti-hallucination.md) | Bộ đo & cơ chế phòng chống hallucination | AI engineer, QA |
| [09-api-ui.md](09-api-ui.md) | REST/SSE contract, layout UI, ràng buộc chat 60% | FE |
| [10-config-secrets.md](10-config-secrets.md) | Config local vs prod, nơi khai báo model & API key | Mọi dev |
| [11-module-spec.md](11-module-spec.md) | Cây thư mục, từng module, signature hàm/class | Dev implement |
| [12-build-deploy.md](12-build-deploy.md) | Build, chạy local, deploy GreenNode AgentBase | DevOps |
| [13-testing-eval.md](13-testing-eval.md) | Unit test, golden set, đo chất lượng agent | QA |
| [14-roadmap-risks.md](14-roadmap-risks.md) | Lộ trình theo sprint, rủi ro, câu hỏi mở | PM |
| [15-streaming.md](15-streaming.md) | Streaming phản hồi, thông báo tiến trình theo giai đoạn | FE + AI eng |
| [16-dev-readiness.md](16-dev-readiness.md) | Tài liệu đã đủ để dev triển khai chưa, còn thiếu gì | **Tech lead / PM** |
| [17-implementation-guide.md](17-implementation-guide.md) | **Hướng dẫn triển khai: 14 nhiệm vụ, mỗi nhiệm vụ có lệnh nghiệm thu** | **Người/agent viết code — bắt đầu từ đây** |
| [adr/](adr/) | Architecture Decision Records — lý do đằng sau từng lựa chọn | Reviewer |

## 3. Tóm tắt kiến trúc trong 10 dòng

```
Excel mock ──ETL──> PostgreSQL (GreenNode VM, dùng chung local+prod)
                          │
                    Semantic Layer (metrics.yml)  ← SQL đã kiểm chứng, không phải LLM tự viết
                          │
   Người dùng ──> FastAPI ──> Agent Orchestrator ──> Tool: metric / guarded-SQL / stats
                          │                                    │
                          │                             Evidence Table (JSON có fact_id)
                          │                                    │
                          │                          Narrator LLM (chỉ viết chữ)
                          │                                    │
                          │                          Verification Pipeline  ← 5 lớp kiểm tra
                          │                                    │
                          └──────────────── Answer + Trust Score + nút "Xem SQL & số liệu"
```

**Nguyên tắc xuyên suốt: _code tính toán — LLM chỉ diễn giải_.** Mọi con số trong câu trả lời phải khớp byte-to-byte với một ô trong kết quả truy vấn, nếu không thì bị chặn.

## 4. Quyết định kiến trúc chính

| Quyết định | Lựa chọn | ADR |
|---|---|---|
| Database | **vDB RDS — PostgreSQL** của GreenNode, Public Endpoint dùng chung local + prod (dự phòng: Docker trên vServer VM) | [ADR-001](adr/ADR-001-database.md) |
| Cách agent truy cập dữ liệu | Semantic layer (metric catalog) trước, free-form SQL chỉ là fallback có rào | [ADR-002](adr/ADR-002-semantic-layer-over-text2sql.md) |
| Chống hallucination | Grounding tất định (deterministic) là lớp chính, LLM-judge là lớp phụ | [ADR-003](adr/ADR-003-hallucination-strategy.md) |
| Phân khúc khách hàng | Rule-based tiering tính bằng code; LLM chỉ đặt tên & kể chuyện | [ADR-004](adr/ADR-004-segmentation.md) |
| UI | FastAPI + Jinja2 + Tailwind + Alpine.js + ECharts (CDN, không build step) | [ADR-005](adr/ADR-005-ui-stack.md) |
| Prompt | File YAML ngoài code, hot-reload, có version & trang admin sửa trực tiếp | [ADR-006](adr/ADR-006-prompt-as-config.md) |

## 5. Nguồn kiểm chứng

Các khẳng định về nền tảng GreenNode (hợp đồng deploy, giới hạn 10 RPM, catalog model, vDB RDS) và về kỹ thuật chống hallucination đều được tra từ tài liệu chính thức. Danh sách đường dẫn, kèm ba điểm mà sổ tay BTC lệch so với tài liệu nền tảng, nằm ở [_sources.md](_sources.md).

Mọi số liệu nghiệp vụ trong tài liệu được đo trực tiếp từ `data/full_schema_mock_v2.xlsx`, không phải ước lượng.

## 6. Hiện vật đã sẵn sàng cho triển khai

Ngoài tài liệu, repo đã có các file cấu hình và hợp đồng **đã kiểm chứng trên dữ liệu thật**:

| Đường dẫn | Nội dung |
|---|---|
| `app/contracts.py` | 14 Protocol + 52 kiểu dữ liệu — đặc tả ở mức class/function |
| `app/errors.py` | 40 mã lỗi, có ánh xạ HTTP và thông báo tiếng Việt |
| `config/semantic/metrics.yml` | 53 chỉ số, 42 chỉ số kèm giá trị đối chứng |
| `config/semantic/entities.yml` | 4 dataset, 25 dimension |
| `config/analytics.yaml` | 8 luật phân khúc, bảng tra `p_repeat`, 6 hành động D3 |
| `config/verify.yaml` | Ngưỡng 7 lớp kiểm chứng |
| `config/stages.yaml` | Thông báo tiến trình streaming |
| `config/playbooks/*.yml` | 9 playbook |
| `prompts/*.yaml` | 9 prompt, 36 few-shot dùng số thật |
| `etl/sql/*.sql` | DDL đầy đủ — đã chạy kiểm chứng, 12/12 bất biến đạt |
| `evals/golden/qa_set.yaml` | 100 ca golden set, 37 ca bẫy |
