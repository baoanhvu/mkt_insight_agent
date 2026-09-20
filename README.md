# Marketing Insight Agent

Agent đọc dữ liệu chiến dịch marketing và hồ sơ vay, tự phân tích và trả lời ba câu hỏi nghiệp vụ:

1. **Dashboard hiệu quả từng chiến dịch** — chiến dịch nào lãi/lỗ, phễu rơi ở đâu, tiền nên dồn vào đâu
2. **Chân dung tập khách hàng tiềm năng** — ai đáng theo đuổi, và bằng chứng nào nói vậy
3. **Hành động nâng cao giá trị vòng đời khách hàng** — làm gì, với ai, kỳ vọng thu về bao nhiêu

Mọi kết luận đều truy vết được xuống dòng dữ liệu gốc. Đây là ràng buộc thiết kế số một, không phải tính năng phụ.

> **Dự án:** MSB x GreenNode AI Hackathon 2026
> **Trạng thái:** Đã implement đầy đủ 14/14 nhiệm vụ (T01–T14), 341 test đang pass, đã deploy PoC lên GreenNode AgentBase Runtime.

## Chạy local

Yêu cầu: Python 3.13, Docker (cho Postgres cục bộ), một API key LLM tương thích OpenAI (GreenNode MaaS hoặc tương đương).

```bash
git clone <url-repo-nay>
cd mkt_insight_agent

python -m venv .venv
.venv/Scripts/activate          # Windows; Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env            # dien LLM_API_KEY that vao .env (KHONG commit file nay)

docker compose -f docker-compose.dev.yml up -d
python -m etl.load_excel --source excel && python -m etl.build_marts && python -m etl.dq_checks

python main.py                  # -> http://localhost:8080  (/health, /readyz)
```

Chạy kiểm tra trước khi coi là xong việc (xem đầy đủ ở [`CLAUDE.md`](CLAUDE.md)):

```bash
python scripts/validate_artifacts.py
python scripts/verify_metrics_duckdb.py
ruff check . && mypy app/semantic app/verify app/analytics && lint-imports
pytest tests/ -q
python -m evals.run_eval --split dev --profile test
```

Deploy lên GreenNode AgentBase: xem [`docs/12-build-deploy.md`](docs/12-build-deploy.md) và `scripts/deploy_greennode.ps1`.

> **Lưu ý bảo mật:** repo này giả định luôn ở chế độ **private** — xem [`docs/10-config-secrets.md`](docs/10-config-secrets.md) §10.5. Không bao giờ commit `config/secrets.yaml`, `.env`, `.greennode.json` (đã có trong `.gitignore`).

## Bắt đầu từ đâu

Toàn bộ thiết kế nằm trong [`docs/`](docs/00-INDEX.md). Đọc theo thứ tự:

| Bạn muốn | Đọc |
|---|---|
| Hiểu bài toán và nguyên tắc | [01 — Tổng quan](docs/01-overview.md) |
| Biết dữ liệu có gì, bẫy ở đâu | [02 — Mô hình dữ liệu](docs/02-data-model.md) |
| Biết dùng DB nào, cài ở đâu | [03 — Chọn database](docs/03-database-choice.md) |
| Xem kiến trúc tổng thể | [04 — Kiến trúc](docs/04-architecture.md) |
| Hiểu cơ chế chống hallucination | [08 — Chống hallucination](docs/08-anti-hallucination.md) |
| Sửa nội dung phân tích | [07 — Prompt & few-shot](docs/07-prompt-fewshot.md) |
| Hiểu luồng streaming & thông báo tiến trình | [15 — Streaming](docs/15-streaming.md) |
| **Bắt tay vào code** | **[17 — Hướng dẫn triển khai](docs/17-implementation-guide.md)** — 14 nhiệm vụ, mỗi nhiệm vụ có lệnh nghiệm thu |
| Xem cây thư mục và signature module | [11 — Đặc tả module](docs/11-module-spec.md) |
| Deploy lên GreenNode | [12 — Build & deploy](docs/12-build-deploy.md) |
| Biết độ sẵn sàng và còn thiếu gì | [16 — Độ sẵn sàng](docs/16-dev-readiness.md) |

## Hiện vật đã sẵn sàng

Ngoài code ứng dụng đầy đủ trong `app/`, các file cấu hình/dữ liệu dưới đây **đã viết xong và kiểm chứng trên dữ liệu thật, là nguồn sự thật** — không viết lại, xem [`CLAUDE.md`](CLAUDE.md) mục "KHÔNG viết lại những file này":

```
app/contracts.py              14 Protocol + 52 kiểu — đặc tả mức class/function
app/errors.py                 40 mã lỗi
config/semantic/metrics.yml   53 chỉ số, 42 chỉ số có giá trị đối chứng
config/semantic/entities.yml  4 dataset, 25 dimension
config/analytics.yaml         8 luật phân khúc, bảng tra p_repeat, 6 hành động
config/verify.yaml            ngưỡng 7 lớp chống hallucination
config/stages.yaml            thông báo tiến trình streaming
config/playbooks/*.yml        9 playbook
prompts/*.yaml                9 prompt, 36 few-shot dùng số thật
etl/sql/*.sql                 DDL đầy đủ — 12/12 bất biến đạt khi chạy thử
evals/golden/qa_set.yaml      100 ca golden set, 37 ca bẫy
```

Lý do đằng sau từng lựa chọn nằm ở [`docs/adr/`](docs/00-INDEX.md#4-quyết-định-kiến-trúc-chính).

## Nguyên tắc cốt lõi

**Code tính toán — LLM chỉ diễn giải.**

LLM không bao giờ tự tính một con số. Mọi con số đến từ SQL đã được viết sẵn và kiểm chứng. LLM nhận một bảng bằng chứng và viết văn xuôi quanh nó, với số được phát ra dưới dạng thẻ tham chiếu. Thẻ nào không phân giải được về một ô dữ liệu thật thì câu trả lời bị chặn.

## Dữ liệu

`data/full_schema_mock_v2.xlsx` — 6 bảng, 24 297 dòng, kỳ dữ liệu 01–31/08/2026.
`data/parquet/` — bản xuất parquet tương ứng, tên cột đã chuẩn hoá.

Ba kết luận nổi bật đã đo được từ dữ liệu này, và chúng là "đáp án" mà agent phải tự tìm ra:

* **Zalo Remarketing (tái vay) có ROMI 6,20** — gấp gần 4 lần kênh thu hút khách mới tốt nhất. Bán cho khách cũ rẻ và lãi hơn nhiều lần so với đi tìm khách mới.
* **Broker Network lỗ 66,8 triệu** dù tỷ lệ lead→hồ sơ cao nhất nhóm khách mới. Phễu đẹp ở đầu, lỗ ở cuối.
* **Khách vay lại sinh lời gấp 20,9 lần** khách chỉ vay một lần — nền tảng của toàn bộ luận điểm CLV.

## Trạng thái

14/14 nhiệm vụ trong [17 — Hướng dẫn triển khai](docs/17-implementation-guide.md) đã hoàn tất: tầng dữ liệu/semantic (T01–T05), dashboard D1/D2/D3 (T06), agent orchestrator + LLM (T07–T08), chuỗi kiểm chứng L2–L5 (T09, T11), streaming SSE (T10), SQL guard + đường freeform (T12), trang admin sửa prompt (T13), đóng gói và deploy GreenNode AgentBase (T14).

Đã deploy bản PoC thật lên GreenNode AgentBase Runtime, dùng chung một vDB RDS PostgreSQL cho cả local và prod (xem [03 — Chọn database](docs/03-database-choice.md) §3.5).
