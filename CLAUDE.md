# Hướng dẫn cho agent-developer

> File này được nạp tự động vào mọi phiên làm việc. Đọc hết trước khi sửa bất kỳ file nào.

## Dự án này là gì

Agent đọc dữ liệu chiến dịch marketing + hồ sơ vay, tự phân tích và trả lời ba câu hỏi: hiệu quả từng chiến dịch (D1), chân dung tập khách tiềm năng (D2), hành động nâng cao CLV (D3).

**Nguyên tắc nền tảng của toàn bộ hệ thống: _code tính toán — LLM chỉ diễn giải._**
LLM không bao giờ tự tính một con số. Mọi con số đến từ SQL đã viết sẵn và đã kiểm chứng. LLM nhận một bảng bằng chứng và viết văn xuôi quanh nó, với số phát ra dưới dạng thẻ `{{F1.r1.romi}}`. Thẻ nào không phân giải được về một ô dữ liệu thật thì câu trả lời bị chặn.

Nếu một thay đổi nào đó làm rò nguyên tắc này, thay đổi đó sai — kể cả khi test vẫn xanh.

## Bắt đầu từ đâu

1. [`docs/17-implementation-guide.md`](docs/17-implementation-guide.md) — 14 nhiệm vụ, mỗi nhiệm vụ có lệnh nghiệm thu
2. [`app/contracts.py`](app/contracts.py) — hợp đồng giữa các module, là đặc tả ở mức class/function
3. [`docs/02-data-model.md`](docs/02-data-model.md) §2.1 và §2.4 — cấu trúc bất thường của dữ liệu và bốn cái bẫy

## Năm quy tắc không được phá

| # | Quy tắc | Cơ chế ép |
|---|---|---|
| R1 | LLM không bao giờ tự tính một con số | `tests/test_numeric_grounding.py` + lớp L2 |
| R2 | Không nối chuỗi dữ liệu người dùng vào SQL — luôn bind parameter | `tests/test_semantic_compiler.py` |
| R3 | `app/analytics/` và `app/verify/` không được import `data`, `llm`, `api` | `lint-imports` trong CI |
| R4 | Không hạ ngưỡng kiểm chứng để test xanh — sửa code, đừng sửa rào | `scripts/validate_artifacts.py` |
| R5 | Không hardcode chuỗi hiển thị tiếng Việt trong `.py` — chúng nằm trong YAML | review |

## Ba điều về dữ liệu, không biết thì code sẽ sai âm thầm

1. **`fact_loan` không có `campaign_id` và không có `lead_id`.** Cầu nối duy nhất tới chiến dịch là `sub_channel`. Viết `JOIN ... ON campaign_id` là lỗi kinh điển — cột đó không tồn tại.
2. **1 062/2 687 hồ sơ bị từ chối có `loan_amount`, `tenure`, `rate`, `balance` đều NULL.** Đúng về nghiệp vụ. `AVG(loan_amount)` ra đúng, nhưng `SUM(loan_amount)/COUNT(*)` sai 39%.
3. **Lợi nhuận lệch cực mạnh:** trung bình +199 629 VND nhưng trung vị **−86 175 VND**, 53,8% khách lỗ, top 10% chiếm 81,9% lợi nhuận. Báo cáo trung bình một mình là gây hiểu nhầm.

## KHÔNG viết lại những file này

Chúng đã viết xong và **đã kiểm chứng trên dữ liệu thật**. Chúng là nguồn sự thật, không phải bản nháp:

```
app/contracts.py              app/errors.py
config/semantic/metrics.yml   config/semantic/entities.yml
config/analytics.yaml         config/verify.yaml         config/stages.yaml
config/app.yaml               config/profiles/*.yaml
config/playbooks/*.yml        prompts/*.yaml
etl/sql/*.sql                 evals/golden/qa_set.yaml
```

Nếu tin rằng một trong số chúng sai: **dừng lại và báo**, kèm lệnh tái hiện. Đừng tự sửa.

Riêng khối `reference` trong `metrics.yml` là giá trị đối chứng đã đo trên dữ liệu thật. Nếu code cho kết quả khác, **code sai chứ không phải `reference` sai**.

## Chạy gì trước khi coi là xong

```bash
python scripts/validate_artifacts.py          # nhat quan cheo cau hinh, khong can DB
python scripts/verify_metrics_duckdb.py       # doi chieu chi so voi du lieu that, khong can DB
ruff check . && mypy app/semantic app/verify app/analytics && lint-imports
pytest tests/ -q
python -m evals.run_eval --split dev --profile test
```

Ba cổng **cứng**, không có ngoại lệ:

* `numeric_grounding_rate` phải bằng **1,000**
* `must_not_mention_violations` phải bằng **0**
* Không có mục DQ mức `BLOCK` nào fail

## Sáu giá trị phải luôn đúng

Nếu code cho ra số khác, có lỗi ở đâu đó — dừng lại và tìm:

| campaign_id | ROMI | Lợi nhuận ròng (VND) |
|---|---:|---:|
| CMP-ZL-RL1 | 6,20 | +392 498 488 |
| CMP-GG-001 | 1,60 | +88 164 340 |
| CMP-FB-001 | 1,31 | +77 767 299 |
| CMP-TT-001 | 0,67 | +35 746 732 |
| CMP-PTN-MOMO | −0,41 | −17 529 775 |
| CMP-PTN-BRK01 | −1,85 | −66 794 874 |

Và: 2 687 hồ sơ · 1 625 giải ngân · 1 062 từ chối · 14 530 lead · 2 901 khách · phân khúc tổng 2 901 với `_unclassified` = 0.

## Khi bị vướng

| Tình huống | Làm gì |
|---|---|
| Chỉ số cho kết quả khác `reference` | **Dừng.** ETL sai hoặc compiler sai. Không sửa `reference` |
| Model viết chữ số thay vì thẻ | Thêm few-shot phản ví dụ → hạ `temperature` xuống 0,1 → đổi model lớn hơn. **Không tắt lớp L2** |
| Test đỏ vì ngưỡng kiểm chứng | Sửa code. Không hạ ngưỡng |
| Câu hỏi hay rơi xuống `freeform` | Tín hiệu **thiếu chỉ số** trong catalog, không phải cần nới rào ở `freeform` |
| Thiếu thông tin trong tài liệu | Ghi `# ASSUMPTION:` ngay tại code rồi báo lại. Đừng im lặng đoán |
| Đụng trần 10 RPM khi dev | Dùng `APP_PROFILE=test` (provider mock) cho mọi test |

## Môi trường

* Python 3.13. Windows là môi trường dev chính.
* `APP_PROFILE` chọn cấu hình: `local` · `greennode` · `test`. Mặc định `local`.
* Database dùng chung cho local và prod (vDB RDS PostgreSQL trên GreenNode). Chỉ `test` trỏ vào Postgres cục bộ qua `docker-compose.dev.yml`.
* AgentBase Runtime **bắt buộc** lắng nghe `0.0.0.0:8080` và có `GET /health` trả 200.
* MaaS giới hạn **10 request/phút cho cả tài khoản** — ngân sách là ≤2 lượt gọi LLM cho một câu hỏi chat, 0 lượt cho dashboard.

## Phong cách

* Comment và docstring trong code: tiếng Việt không dấu (tránh lỗi encoding trên Windows console).
* Chuỗi hiển thị cho người dùng: tiếng Việt có dấu, và nằm trong file YAML chứ không trong `.py`.
* Type hint bắt buộc ở mọi hàm public. `mypy --strict` cho `semantic/`, `verify/`, `analytics/`.
* Không `raise Exception(...)` trần — dùng cây lỗi trong `app/errors.py`.
