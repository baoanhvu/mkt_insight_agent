# ADR-004 — Phân khúc bằng luật tường minh, không bằng k-means

**Trạng thái:** Đã chốt · **Ngày:** 2026-09-19 · Liên quan: [06](../06-agent-design.md) §6.6

## Bối cảnh

Deliverable D2 yêu cầu "chân dung các tập khách hàng tiềm năng". Hai hướng: phân cụm không giám sát (k-means trên các đặc trưng khách hàng), hoặc phân tầng bằng luật nghiệp vụ.

Profiling cho thấy ba chiều thật sự phân hoá và bốn chiều thì không:

| Chiều | Tỷ lệ vay lại | Kết luận |
|---|---|---|
| Thu nhập | 7,5% → 20,7% (n=657 → 797) | **Phân hoá mạnh** |
| Có app | 10,3% → 16,6% | **Phân hoá** |
| Tuổi | 8,8% → 21,6% | **Phân hoá** |
| Nghề nghiệp | 12,8% – 14,5%, lợi nhuận TB 180k–220k trên n≈360, σ cá thể 738k | **Nhiễu** |

## Quyết định

Phân khúc tính bằng **tám luật tường minh**, chạy theo thứ tự, mỗi khách rơi vào phân khúc đầu tiên khớp:

`high_risk` → `champion` → `repeat_standard` → `high_potential` → `app_gap` → `dormant` → `rejected_only` → `never_activated`

Bất biến: **`_unclassified` luôn bằng 0**. Tổng tám phân khúc = 2 901 khách.

Định nghĩa gốc ở `config/analytics.yaml → segmentation.rules`; bản SQL tương đương ở `etl/sql/02_ddl_mart.sql → mart.v_customer_segment`. Hai bản phải khớp, và `tests/test_segmentation.py` khẳng định điều đó.

LLM chỉ **đặt tên hiển thị và kể chuyện** về các phân khúc đã tính xong. Nó không tham gia vào việc quyết định ai thuộc phân khúc nào.

`occupation` **không** được dùng làm trục phân khúc, chỉ giữ làm thuộc tính mô tả kèm ghi chú rằng nó không phân biệt được giá trị.

K-means giữ lại như một chế độ đối chứng offline (`--mode kmeans`), không bao giờ là nguồn cho câu trả lời gửi người dùng.

## Lý do

* Một phân khúc là cơ sở để chi tiền marketing. Nó phải **tái lập được, giải thích được cho kiểm toán, và ổn định giữa hai lần chạy**. K-means không cho cả ba: đổi seed hay đổi k là đổi phân khúc.
* Với 2 554 khách hàng và vài đặc trưng, k-means sẽ chủ yếu bám vào `income` và `profit_to_date` — tức là tái phát hiện đúng thứ luật đã mã hoá, nhưng dưới dạng không giải thích được.
* Luật kết nối trực tiếp với hành động. `app_gap` không chỉ là một cụm — nó là một danh sách khách cụ thể kèm một hành động cụ thể ("đẩy cài app") và một công thức ước lượng tác động.
* Loại `occupation` khỏi trục phân khúc là quyết định dựa trên bằng chứng, và nó ngăn việc tạo ra những phân khúc trông sâu sắc nhưng thực chất là nhiễu.

## Phương án đã cân nhắc

| Phương án | Vì sao loại |
|---|---|
| K-means / phân cụm phân cấp | Không giải thích được; không ổn định; không gắn với hành động |
| RFM cổ điển (Recency-Frequency-Monetary) | Chỉ có 31 ngày giao dịch, Recency gần như vô nghĩa. Vẫn dùng ý tưởng giá trị + tần suất, nhưng không dùng ô lưới RFM |
| Để LLM tự đề xuất phân khúc | Không tái lập được; mời gọi việc bịa ra phân khúc không tồn tại |

## Hai lỗi phát hiện khi kiểm chứng trên dữ liệu thật

Bộ luật ban đầu có sáu luật. Khi chạy thật, nó hỏng ở hai chỗ — cả hai đều đáng ghi lại vì chúng dễ lặp lại:

**Lỗi 1 — `_unclassified` chiếm 36,7%.** 1 064 khách rơi vào lưới an toàn, chủ yếu là nhóm đã nộp hồ sơ nhưng chưa bao giờ được giải ngân, vì mọi luật đều yêu cầu `n_disbursed >= 1`. Một lưới an toàn bắt hơn một phần ba tập khách không phải lưới an toàn — nó là bằng chứng bộ luật chưa hoàn chỉnh. Sửa bằng cách thêm `rejected_only` và `repeat_standard`.

**Lỗi 2 — `high_risk` đứng cuối nên gần như vô hiệu.** Nó chỉ bắt được 15 khách, vì một khách vay lại nhiều lần và nợ quá hạn 60 ngày đã bị luật `champion` bắt trước. Sau khi chuyển `high_risk` lên đầu, nó bắt đúng 97 khách — trong đó 25 khách là `is_repeat_customer`. Nguyên tắc: **rủi ro ghi đè mọi thuộc tính khác.**

Phân bố sau khi sửa (đã kiểm chứng):

| Phân khúc | n | % | LN trung bình | LN trung vị |
|---|---:|---:|---:|---:|
| `rejected_only` | 1 023 | 35,3% | −140 451 | −140 551 |
| `dormant` | 802 | 27,6% | 305 061 | 293 219 |
| `never_activated` | 347 | 12,0% | 0 | 0 |
| `champion` | 282 | 9,7% | 1 423 972 | 1 276 482 |
| `app_gap` | 159 | 5,5% | 327 085 | 330 648 |
| `high_potential` | 145 | 5,0% | 303 559 | 271 814 |
| `high_risk` | 97 | 3,3% | −936 131 | −382 047 |
| `repeat_standard` | 46 | 1,6% | 45 579 | −90 022 |

## Hệ quả

**Tích cực:** phân khúc giải thích được bằng một câu; ổn định tuyệt đối; test được (tổng = 100%, `_unclassified` = 0, mỗi khách đúng một phân khúc); nối thẳng vào thư viện hành động của D3.

**Tiêu cực:** có thể bỏ sót một cấu trúc chưa ai nghĩ tới — giảm thiểu bằng chế độ k-means đối chứng chạy offline. Nếu k-means tìm ra cụm mà luật không có, **bổ sung luật**, không thay luật bằng k-means.

**Cần bảo trì:** ngưỡng trong luật (`P75_PROFIT`, các dải thu nhập) phải xem lại khi dữ liệu thay đổi đáng kể. Chúng nằm trong `config/analytics.yaml` chứ không hardcode.
