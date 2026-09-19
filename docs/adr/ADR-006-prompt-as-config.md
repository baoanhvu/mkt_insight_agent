# ADR-006 — Prompt là cấu hình, không phải mã nguồn

**Trạng thái:** Đã chốt · **Ngày:** 2026-09-19 · Liên quan: [07](../07-prompt-fewshot.md)

## Bối cảnh

Yêu cầu gốc: *"Nội dung phân tích, tôi muốn có thể chỉnh sửa sau, do đó cần hỗ trợ prompt, few-shot."*

Người sửa nội dung phân tích là marketing lead và business analyst, không phải dev. Nếu mỗi lần đổi giọng văn hay thêm một mục trong báo cáo đều phải nhờ dev sửa code và deploy lại, tính năng đó coi như không tồn tại.

Đồng thời có một rủi ro cần chặn: người sửa prompt **không được** vô tình làm sai số liệu hoặc nới lỏng rào chống hallucination.

## Quyết định

Tách làm bốn tầng sửa được, mỗi tầng một file riêng và một nhóm người phụ trách:

| Tầng | File | Đổi cái gì | Ai |
|---|---|---|---|
| T1 | `config/semantic/metrics.yml` | Con số | Data analyst |
| T2 | `config/playbooks/*.yml` | Nói về cái gì | Business analyst |
| T3 | `prompts/*.yaml` | Cách nói | Marketing lead |
| T4 | `config/verify.yaml` | Ngưỡng kiểm chứng | AI engineer |

Prompt là file YAML độc lập, gồm: `system`, `instructions` (Jinja2), `few_shots`, `params`, `output_contract`, và `version`. Hot-reload theo `mtime`. Có trang `/admin/prompts` để sửa, chạy thử và khôi phục.

Trong môi trường nhiều replica, bản sửa qua UI ghi vào `ops.prompt_override` trong Postgres; file trong image là baseline.

## Lý do

* **Tách bạch rõ ràng: prompt điều khiển ngôn ngữ, config điều khiển sự thật.** Sửa prompt có thể làm câu trả lời xấu đi, nhưng không thể làm con số sai — vì con số đến từ semantic layer và được kiểm chứng ở tầng render. Đó là lý do trao quyền sửa prompt cho business user là an toàn.
* Hot-reload nghĩa là vòng lặp sửa–thử tính bằng giây, không phải bằng chu kỳ deploy.
* `version` trong mỗi prompt đi thẳng vào `ops.agent_trace.prompt_version`. Không có nó thì khi chất lượng tụt, không ai phân biệt được là do sửa prompt, đổi model, hay dữ liệu thay đổi.
* `output_contract` với `forbidden_patterns` cho phép bắt lỗi định dạng **trước khi** câu trả lời đi qua các lớp kiểm chứng đắt hơn.
* Nút "chạy golden set" ngay trên trang admin biến việc sửa prompt từ một hành động mù thành một hành động có phản hồi đo được.

## Phương án đã cân nhắc

| Phương án | Vì sao loại |
|---|---|
| Prompt là hằng số trong `.py` | Sửa phải deploy lại; business user không đụng được; không version độc lập |
| Prompt trong biến môi trường | Prompt nhiều dòng trong env var là ác mộng; không có few-shot có cấu trúc |
| Prompt trong database từ đầu | Thêm phụ thuộc lúc khởi động, khó review qua git. Chọn cách lai: file là baseline, DB là override |
| Dùng thư viện quản lý prompt bên ngoài | Thêm phụ thuộc ngoài, thêm điểm hỏng, và phải có mạng lúc khởi động |

## Hệ quả

**Tích cực:** business user tự sửa được; hot-reload dưới 5 giây; mọi thay đổi có version và khôi phục được; prompt review được qua git như mã nguồn.

**Tiêu cực:** YAML sai cú pháp có thể lọt vào lúc chạy — giảm thiểu bằng việc **giữ nguyên bản đang chạy** khi parse lỗi và ghi log, thay vì làm sập agent. Trang admin chưa có phân quyền ở PoC, chỉ bảo vệ bằng `X-Admin-Token`.

**Ranh giới phải giữ:** công thức chỉ số, ngưỡng kiểm chứng, cỡ mẫu tối thiểu, và danh sách bảng/cột thật **không bao giờ** được đưa vào prompt. Đưa schema thô vào prompt là mời LLM viết SQL tự do — đúng thứ [ADR-002](ADR-002-semantic-layer-over-text2sql.md) đang tránh. Còn để prompt tự nới ngưỡng của bộ kiểm chứng thì hàng rào tự vô hiệu hoá chính nó.
