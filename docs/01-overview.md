# 01 — Tổng quan, phạm vi & nguyên tắc thiết kế

## 1.1 Bối cảnh

Bài toán đến từ một tổ chức cho vay tiêu dùng số (unsecured consumer lending). Mỗi tháng có hàng chục nghìn lead đổ về từ 6 chiến dịch trên 6 kênh khác nhau (Facebook, Google, TikTok, Zalo, Momo, Broker). Mỗi lead có thể trở thành hồ sơ vay, hồ sơ có thể bị từ chối hoặc được giải ngân, và mỗi khoản vay sinh ra một dòng P&L riêng.

Câu hỏi mà đội marketing đang phải tự trả lời bằng Excel:

* Tiền quảng cáo đang chảy vào chiến dịch nào, và chiến dịch đó **thực sự lãi hay lỗ** sau khi trừ chi phí vốn, chi phí rủi ro, phí đối tác?
* Tập khách nào nên nhắm tới, dựa trên bằng chứng chứ không phải cảm tính?
* Hành động cụ thể nào làm tăng giá trị vòng đời khách hàng (CLV), và đáng bao nhiêu tiền?

Việc trả lời thủ công mất vài ngày mỗi chu kỳ và không lặp lại được. Agent này nén chu kỳ đó xuống vài giây, với điều kiện **kết quả phải tin được**.

## 1.2 Mục tiêu PoC

| Mã | Mục tiêu | Tiêu chí nghiệm thu |
|---|---|---|
| G1 | Dashboard hiệu quả chiến dịch | 6 chiến dịch × 15 chỉ số, khớp 100% với truy vấn SQL đối chứng |
| G2 | Chân dung tập KH tiềm năng | ≥ 4 phân khúc, mỗi phân khúc có size, CLV, repeat rate, và **khoảng tin cậy** |
| G3 | Khuyến nghị hành động nâng CLV | Mỗi khuyến nghị gắn với 1 phân khúc, 1 chỉ số mục tiêu, 1 ước lượng tác động có công thức |
| G4 | Nội dung phân tích sửa được không cần code | Business user sửa file YAML/qua trang admin, reload < 5 giây |
| G5 | Bộ đo chống hallucination | Mọi câu trả lời có Trust Score; numeric grounding ≥ 99% trên golden set |
| G6 | Chạy được cả local và GreenNode AgentBase | Cùng codebase, khác profile model, chung 1 database |

## 1.3 Ngoài phạm vi (Non-goals)

Ghi rõ để không bị scope creep giữa hackathon:

* ❌ Không làm real-time streaming — dữ liệu batch, refresh theo lịch.
* ❌ Không train model ML riêng. CLV dùng công thức minh bạch, phân khúc dùng rule; k-means chỉ là tuỳ chọn.
* ❌ Không làm hệ thống phân quyền người dùng (RBAC). PoC dùng 1 vai trò duy nhất.
* ❌ Không tích hợp ngược vào hệ thống gửi campaign (Zalo ZNS, CRM). Agent chỉ **đề xuất** hành động, xuất ra danh sách khách hàng dạng CSV.
* ❌ Không làm data lineage / catalog đầy đủ. Semantic layer đủ dùng cho 6 bảng.
* ⚠️ Zalo bot (Bước 3 của BTC) để **tuỳ chọn** — kiến trúc có chừa cổng vào, nhưng không nằm trong đường găng.

## 1.4 Người dùng và kịch bản sử dụng

**Persona A — Linh, Digital Marketing Lead.** Mở dashboard mỗi sáng thứ Hai. Cần biết ngay: chiến dịch nào âm ROMI tuần này, và nên cắt ngân sách chỗ nào. Hỏi agent: *"Tại sao Broker Network lỗ?"* → cần câu trả lời phân rã được xuống từng khoản chi phí.

**Persona B — Đức, CRM Manager.** Cần danh sách khách hàng để chạy campaign tái vay. Hỏi: *"Tập nào có khả năng vay lại cao nhất?"* → cần kèm file CSV customer_id để đẩy sang hệ thống gửi tin.

**Persona C — Chị Hà, Head of Retail Lending.** Không hỏi chi tiết, chỉ đọc 5 dòng tóm tắt và 3 khuyến nghị. Nhưng khi chất vấn thì cần bằng chứng ngay tại chỗ.

→ Hệ quả kiến trúc: UI phải có **cả dashboard lẫn chat**, và mọi số liệu phải bấm vào xem được SQL sinh ra nó.

## 1.5 Bảy nguyên tắc thiết kế

Đây là những quy tắc mà mọi quyết định code sau này phải tuân theo. Khi phân vân, quay lại đây.

### P1 — Code tính toán, LLM diễn giải
LLM **không bao giờ** được tự tính một con số. Mọi con số đến từ SQL đã chạy. LLM nhận vào một bảng bằng chứng (evidence table) dạng JSON và viết văn xuôi quanh nó. Đây là khác biệt nền tảng so với việc "đưa CSV vào prompt rồi hỏi".

### P2 — Không có số nào không có nguồn
Mỗi con số xuất hiện trong câu trả lời phải map ngược về một ô cụ thể `(query_id, row_index, column)`. Cơ chế thực thi nằm ở [08-anti-hallucination.md](08-anti-hallucination.md). Số không map được → câu trả lời bị chặn hoặc gắn cờ.

### P3 — Thà im lặng còn hơn bịa
Khi dữ liệu không đủ trả lời (mẫu quá nhỏ, chỉ số không tồn tại, khoảng thời gian không có dữ liệu), agent phải nói *"không đủ dữ liệu để kết luận"* kèm lý do. Abstention rate là một **chỉ số sức khoẻ**, không phải lỗi.

### P4 — Nội dung phân tích là cấu hình, không phải code
Prompt, few-shot, định nghĩa chỉ số, ngưỡng cảnh báo, cấu trúc báo cáo — tất cả nằm trong file YAML ngoài `app/`. Sửa chúng không cần build lại, không cần dev.

### P5 — Một nguồn sự thật cho định nghĩa chỉ số
"ROMI" chỉ được định nghĩa đúng một lần, trong `config/semantic/metrics.yml`. Dashboard, chat, export CSV, eval set đều gọi cùng một định nghĩa đó. Không có chuyện dashboard hiện 1.31 còn chat nói 1.28.

### P6 — Khác biệt phải có ý nghĩa thống kê mới được gọi là khác biệt
Dữ liệu thật trong bộ mock cho thấy lợi nhuận trung bình theo nghề nghiệp dao động 180k–220k VND trên n≈360 mỗi nhóm — **đây là nhiễu, không phải tín hiệu**. Một LLM không được rào sẽ hân hoan tuyên bố "Freelancer là nhóm sinh lời nhất". Agent phải chạy kiểm định trước khi phát biểu so sánh. Xem [08](08-anti-hallucination.md) §4.

### P7 — Cùng một codebase cho local và prod
Khác biệt duy nhất là profile cấu hình (model nào, endpoint nào). Không có nhánh `if is_production`. Xem [10-config-secrets.md](10-config-secrets.md).

## 1.6 Ràng buộc đã chốt với người đặt bài

| Ràng buộc | Quyết định thiết kế kéo theo |
|---|---|
| Local và Prod dùng **chung 1 database** | DB đặt trên GreenNode, public endpoint có TLS + IP allowlist; không có DB local riêng (chỉ có docker-compose làm mirror offline tuỳ chọn) |
| DB phải **cài/chạy trên GreenNode** | PostgreSQL trong Docker trên GreenNode VM — xem [03](03-database-choice.md) |
| Chat chiếm **tối đa 60% màn hình** | `max-height: 60vh` cho vùng cuộn hội thoại; composer và dashboard nằm ngoài 60% đó — xem [09](09-api-ui.md) §3 |
| UI dùng **thư viện/framework có sẵn** | Tailwind + Alpine.js + ECharts qua CDN, không tự viết component từ đầu, không cần build step |
| Model local ≠ model prod | `config/profiles/{local,greennode}.yaml`, chọn bằng biến `APP_PROFILE` |
| **Model & API key tạm lưu trong repo** | Gom vào đúng 1 file `config/secrets.yaml`, đọc qua 1 lớp duy nhất để sau này đổi sang env/secret manager chỉ sửa 1 chỗ. Repo phải để **private**; rotate key sau hackathon |
| Build/deploy theo **HD_cua_BTC** | Import `greennode-agentbase-skills` vào repo trước khi build; deploy lên Agent Runtime — xem [12](12-build-deploy.md) |

## 1.7 Bản chất kỹ thuật của bài toán này

Một điểm cần nói rõ vì nó định hình toàn bộ thiết kế chống hallucination:

**Đây không phải RAG trên văn bản. Đây là analytics trên dữ liệu có cấu trúc.**

Tài liệu tham khảo của AWS về phát hiện hallucination cho hệ RAG giả định bằng chứng là các đoạn văn bản, và dùng LLM-as-a-judge để đo mức độ "được chống đỡ" của câu trả lời. Cách đó đúng và chúng ta có dùng — nhưng nó là **lớp phụ**.

Với dữ liệu có cấu trúc, ta có một lợi thế mà RAG văn bản không có: **bằng chứng là những con số chính xác**. Nghĩa là phần lớn việc kiểm tra có thể làm **tất định, không cần LLM, không tốn token, không có độ trễ đáng kể**:

* Số `192,3 triệu` trong câu trả lời có xuất hiện trong kết quả truy vấn không? → so khớp chuỗi sau chuẩn hoá. Chính xác 100%.
* Câu trả lời nói "Google Ads cao nhất" — kết quả truy vấn có xác nhận thứ hạng đó không? → sort rồi so. Chính xác 100%.
* Nhóm được khen "tốt hơn hẳn" có n=29 — có đủ mẫu để kết luận không? → z-test. Chính xác 100%.

Một LLM-judge chỉ được gọi đến khi các lớp tất định đã xong, để bắt loại lỗi còn lại: **suy diễn nhân quả không có cơ sở** ("vì TikTok nhắm sai đối tượng nên..."), thứ mà không công thức nào bắt được.

Thứ tự ưu tiên vì thế là: **chặn từ thiết kế > kiểm tra tất định > LLM-judge > con người review**.
