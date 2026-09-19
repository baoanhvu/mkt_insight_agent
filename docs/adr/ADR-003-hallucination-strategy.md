# ADR-003 — Grounding tất định là lớp chính, LLM-judge là lớp phụ

**Trạng thái:** Đã chốt · **Ngày:** 2026-09-19 · Liên quan: [08](../08-anti-hallucination.md)

## Bối cảnh

Người đặt bài yêu cầu một bộ đo và cơ chế chống hallucination, tham chiếu bài viết của AWS về phát hiện hallucination cho hệ RAG. Bài viết đó đề xuất bốn cách — LLM-as-a-judge, tương đồng ngữ nghĩa, BERT stochastic, tương đồng token — và khuyến nghị **cascade**: lọc rẻ trước, judge sau.

Hai dữ kiện định hình quyết định:

1. Bài toán này **không phải RAG trên văn bản**. Bằng chứng là một bảng số chính xác, đọc được bằng máy — không phải prose mờ nhoè.
2. MaaS của GreenNode giới hạn **10 request/phút cho cả tài khoản**. Một kiến trúc tiêu nhiều lượt gọi cho việc kiểm tra sẽ không chạy nổi.

## Quyết định

Xây bảy lớp, sắp theo thứ tự rẻ-và-chắc-chắn trước:

| Lớp | Nội dung | Lượt LLM |
|---|---|---|
| L0 | SQL AST + schema binding (`sqlglot`) | 0 |
| L1 | `EXPLAIN` dry-run dưới role chỉ đọc | 0 |
| **L2** | **Numeric grounding theo giao thức Proof-Carrying Numbers** | **0** |
| L3 | Entity grounding + kiểm tra caveat bắt buộc | 0 |
| L4 | Stats guard — kiểm định trước mọi phát biểu so sánh | 0 |
| L5 | LLM judge theo cấu trúc của bài viết AWS, **chạy bất đồng bộ** | 1 |
| L6 | Trust Score + cổng abstain + telemetry | 0 |

Trust Score dùng **tích có trọng số kèm tập hard-fail**, không phải trung bình cộng. `numeric_grounding_rate < 1,0` là hard fail tuyệt đối.

## Lý do

* Với dữ liệu có cấu trúc, phần lớn việc kiểm tra làm được tất định: *"số 392.498.500 có xuất hiện trong kết quả truy vấn không"* là một phép so khớp chuỗi sau chuẩn hoá, chính xác 100%, tốn vài micro giây.
* Chính số liệu trong bài viết AWS ủng hộ lựa chọn này: bộ judge dùng LLM đạt precision 0,94 nhưng **recall chỉ 0,53** — bỏ sót gần một nửa. Nó không thể là phòng tuyến chính. Ngược lại, bộ so khớp token đạt precision 0,96 ở recall 0,03 — hình mẫu của một bộ lọc rẻ và đáng tin khi nó lên tiếng. Lớp L2 của ta cùng hình mẫu đó nhưng recall cao hơn hẳn vì bằng chứng có cấu trúc.
* Giao thức Proof-Carrying Numbers đẩy việc xác minh xuống **tầng render** và mặc định **fail-closed**: chỉ số nào qua kiểm tra mới được đánh dấu đã xác minh. Điều này làm việc bịa số trở thành bất khả thi về mặt cấu trúc, chứ không chỉ là khó.
* Lớp L4 là bắt buộc với bộ dữ liệu này: chênh lệch lợi nhuận theo nghề nghiệp là nhiễu (180k–220k trên n≈360, σ cá thể 738k), và **không lớp grounding nào bắt được lỗi này** vì con số đó có thật trong kết quả truy vấn.
* Trần 10 RPM khiến việc chạy K lượt (tương đồng ngữ nghĩa) hay N+1 lượt (BERT stochastic) là không khả thi.

## Phương án đã cân nhắc

| Phương án | Vì sao loại |
|---|---|
| Chỉ dùng LLM-judge | Recall 0,53; tốn quota; bỏ sót lỗi thống kê hoàn toàn |
| Tương đồng ngữ nghĩa bằng embedding | Chi phí tỷ lệ với số câu; độ chính xác 0,48 trong đo lường của AWS |
| BERT stochastic (SelfCheckGPT) | N+1 lượt sinh — không thể dưới trần 10 RPM |
| Bedrock Guardrails contextual grounding | Không tự host được, phụ thuộc AWS, và tài liệu ghi rõ không hỗ trợ ca hội thoại nhiều lượt |
| Không làm gì, tin vào prompt | Chính là thứ bài toán yêu cầu giải quyết |

## Hệ quả

**Tích cực:** 11 trên 14 kiểu lỗi bị chặn mà không tốn lượt gọi LLM nào; độ trễ kiểm tra dưới 50 ms; hard fail trên numeric grounding làm việc bịa số trở nên bất khả thi; toàn bộ kết quả kiểm tra ghi vào telemetry nên đo được xu hướng.

**Tiêu cực:** narrator phải tuân thủ định dạng thẻ — nếu model yếu thì tỷ lệ bị chặn tăng (có đường lui ở [14](../14-roadmap-risks.md) R3). Judge bất đồng bộ nghĩa là trong vài giây đầu câu trả lời hiển thị chưa có điểm judge — chấp nhận được **chính vì** L2–L4 mới là lớp chính.

**Ngưỡng:** `t_high` và `t_low` khởi tạo 0,85 / 0,60 là **chỗ đặt tạm**. Không tài liệu nào công bố ngưỡng đúng cho mọi domain. Cổng chặn chỉ được bật sau khi hiệu chỉnh trên golden set bằng đường cong coverage–risk.
