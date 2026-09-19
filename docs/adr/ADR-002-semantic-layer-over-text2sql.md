# ADR-002 — Semantic layer làm đường chính, text-to-SQL chỉ là đường thoát

**Trạng thái:** Đã chốt · **Ngày:** 2026-09-19 · Liên quan: [05](../05-semantic-layer.md)

## Bối cảnh

Agent cần trả lời câu hỏi nghiệp vụ trên dữ liệu có cấu trúc. Cách phổ biến là đưa schema vào prompt và để LLM viết SQL.

Bộ dữ liệu này có ba đặc điểm khiến cách đó nguy hiểm:

1. `fact_loan` **không có** `campaign_id` và **không có** `lead_id`. Cầu nối duy nhất tới chiến dịch là `sub_channel`. Một LLM đọc tên bảng sẽ gần như chắc chắn viết `JOIN ... ON campaign_id` — cột không tồn tại.
2. 1 062 hồ sơ bị từ chối có `loan_amount` NULL. Chọn sai mẫu số làm lệch trung bình tới 39%.
3. Không có cột `status`; trạng thái phải suy ra từ ba điều kiện.

Ba thứ này không phải lỗi dữ liệu — chúng là cấu trúc nghiệp vụ mà chỉ con người biết.

## Quyết định

LLM **không viết SQL**. Nó chọn chỉ số từ một catalog đã khai báo (`config/semantic/metrics.yml`), phát ra một `MetricRequest` có kiểu chặt, và một compiler sinh SQL đã tham số hoá.

Free-form SQL vẫn tồn tại nhưng là **đường thoát**, đi qua bảy cửa kiểm tra (AST parse, chỉ `SELECT`, schema binding trên cây cú pháp, chỉ schema `mart`, bắt buộc `LIMIT`, `EXPLAIN` dry-run, self-consistency tuỳ chọn), và tối đa 3 lần sửa lỗi.

## Lý do

* Ba loại lỗi trên bị chặn **từ thiết kế**, không phải bị phát hiện sau khi đã xảy ra.
* "ROMI" được định nghĩa đúng một lần. Dashboard, chat, export và eval dùng chung định nghĩa đó — không thể có chuyện dashboard hiện 1,31 còn chat nói 1,28.
* Định nghĩa chỉ số trở thành thứ **test được**: `test_metrics_contract.py` khoá sáu giá trị ROMI tham chiếu.
* Tiết kiệm lượt gọi LLM — quan trọng dưới trần 10 RPM của MaaS.
* Business analyst sửa được định nghĩa mà không cần đụng code.

## Phương án đã cân nhắc

| Phương án | Vì sao loại |
|---|---|
| Text-to-SQL thuần | Ba loại lỗi trên xảy ra thường xuyên và một số loại **không báo lỗi**, chỉ cho số sai |
| Nhồi toàn bộ dữ liệu vào prompt | 24k dòng vượt context; và LLM tự cộng trừ là nguồn sai số trực tiếp |
| Chỉ dùng view SQL cố định, không có catalog | Không lọc/nhóm động được; mỗi câu hỏi mới cần một view mới |

## Hệ quả

**Tích cực:** ba lớp lỗi bị loại bỏ từ gốc; nguồn sự thật duy nhất; catalog sửa được không cần dev; ít lượt gọi LLM hơn.

**Tiêu cực:** phải viết và bảo trì catalog; câu hỏi ngoài catalog rơi xuống đường free-form chậm hơn và bị rào chặt hơn. Đây là đánh đổi có chủ ý — **một agent trả lời được ít câu nhưng luôn đúng tốt hơn một agent trả lời mọi câu nhưng thỉnh thoảng bịa.**

`abstain_rate` được theo dõi hằng ngày, và những câu bị từ chối vì thiếu chỉ số chính là danh sách ưu tiên để mở rộng catalog.
