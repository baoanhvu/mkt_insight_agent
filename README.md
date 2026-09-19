# Marketing Insight Agent

Agent đọc dữ liệu chiến dịch marketing và hồ sơ vay, tự phân tích và trả lời ba câu hỏi nghiệp vụ:

1. **Dashboard hiệu quả từng chiến dịch** — chiến dịch nào lãi/lỗ, phễu rơi ở đâu, tiền nên dồn vào đâu
2. **Chân dung tập khách hàng tiềm năng** — ai đáng theo đuổi, và bằng chứng nào nói vậy
3. **Hành động nâng cao giá trị vòng đời khách hàng** — làm gì, với ai, kỳ vọng thu về bao nhiêu

Mọi kết luận đều truy vết được xuống dòng dữ liệu gốc. Đây là ràng buộc thiết kế số một, không phải tính năng phụ.

> **Dự án:** MSB x GreenNode AI Hackathon 2026
> **Trạng thái:** Thiết kế v1.0 — chưa implement

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

Repo không chỉ có tài liệu. Các file dưới đây **đã viết xong và kiểm chứng trên dữ liệu thật** — người triển khai dùng trực tiếp, không viết lại:

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

Tài liệu thiết kế đã hoàn tất. Thứ tự implement ở [11 §11.8](docs/11-module-spec.md), lộ trình theo giai đoạn ở [14](docs/14-roadmap-risks.md).
