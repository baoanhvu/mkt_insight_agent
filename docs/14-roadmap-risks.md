# 14 — Lộ trình, rủi ro và câu hỏi mở

## 14.1 Lộ trình theo giai đoạn

Thứ tự được sắp để **luôn có một sản phẩm demo được** ở cuối mỗi giai đoạn. Nếu hết thời gian ở bất kỳ điểm nào, vẫn có thứ để trình bày.

### Giai đoạn 0 — Nền móng dữ liệu

| Việc | Nghiệm thu |
|---|---|
| Tạo vDB RDS PostgreSQL trên GreenNode, mở Public Endpoint, siết Security Group | `psql` từ máy dev nối được |
| Chạy `00_roles.sql`: 3 role, `default_transaction_read_only` cho agent | `INSERT` bằng `mkt_agent_ro` **bị từ chối** |
| `etl/load_excel.py` + `build_marts.py` + `dq_checks.py` | `SELECT COUNT(*)` ra 2 687 / 1 062 / 1 625; không có DQ mức BLOCK |

**Demo được:** chưa có UI, nhưng có thể mở psql chứng minh dữ liệu và bất biến.

### Giai đoạn 1 — Dashboard không cần LLM

| Việc | Nghiệm thu |
|---|---|
| `semantic/` — catalog chỉ số + compiler | `test_metrics_contract.py` khớp 6 ROMI tham chiếu |
| `data/` — 3 engine, repository | |
| `api/routes_dashboard` + UI tab Chiến dịch | Sáu chiến dịch, ROMI Broker hiện −1,85 tô đỏ |

**Demo được:** dashboard D1 đầy đủ, số chính xác tuyệt đối, **không có khả năng hallucination vì không có LLM**.

### Giai đoạn 2 — Chân dung và hành động, vẫn không cần LLM

| Việc | Nghiệm thu |
|---|---|
| `analytics/stats.py` — Wilson CI, z-test, bootstrap | Đối chiếu giá trị tính tay |
| `analytics/segmentation.py` — 6 luật phân khúc | Tổng phân khúc = 100% số khách |
| `analytics/clv.py` — CLV kèm khoảng | Nhóm ≥20M (n=29) trả `INSUFFICIENT_SAMPLE` |
| Thư viện hành động `clv_actions.yml` + tab Hành động | Mỗi khuyến nghị đủ 5 thành phần |
| UI tab Chân dung + tab Hành động | Thanh sai số hiện trên biểu đồ tỷ lệ vay lại |

**Demo được:** cả ba deliverable D1, D2, D3. Đây là **cột mốc an toàn** — nếu MaaS gặp sự cố hoặc hết quota đúng ngày demo, phần này vẫn chạy.

### Giai đoạn 3 — Lớp hội thoại

| Việc | Nghiệm thu |
|---|---|
| `llm/client.py` — OpenAI-compatible, token bucket 8 RPM, retry | Không bao giờ nhận 429 |
| `prompts/` — 9 file YAML, hot-reload | Sửa file, không restart, có hiệu lực trong 5s |
| `agent/` — orchestrator, router, planner, narrator | |
| `api/routes_chat` SSE + UI tab Hỏi đáp | Chat trả lời, vùng chat ≤ 60vh |

**Demo được:** hỏi đáp tự nhiên trên dashboard.

### Giai đoạn 4 — Hàng rào chống hallucination

| Việc | Nghiệm thu |
|---|---|
| `verify/numeric.py` (L2) + thẻ PCN trong narrator | Câu trả lời cố viết số trực tiếp → bị chặn |
| `verify/entity.py` (L3) + kiểm tra caveat | |
| `verify/stats_guard.py` (L4) | Hỏi "nghề nào sinh lời nhất" → trả lời nói rõ "trong sai số thống kê" |
| Huy hiệu Trust + panel bằng chứng | Bấm xem được SQL và dòng dữ liệu |
| Golden set 100 ca + `evals/run_eval.py` | `numeric_grounding_rate = 1,000` |

**Demo được:** đây là phần tạo khác biệt lớn nhất trước ban giám khảo. Có thể cố tình hỏi câu bẫy và cho thấy agent không sập bẫy.

### Giai đoạn 5 — Đưa lên GreenNode

| Việc | Nghiệm thu |
|---|---|
| `main.py` + `Dockerfile` + `.greennode.json` | Build amd64 thành công |
| Push vCR, tạo Runtime, `poc: true` | Trạng thái `ACTIVE` |
| Kiểm tra endpoint thật | `/health`, `/readyz`, `/`, `/invocations` đều xanh |
| Đối chiếu số local vs prod | Phải trùng khít — chung một DB |

### Giai đoạn 6 — Hoàn thiện (nếu còn thời gian)

| Việc | Ưu tiên |
|---|---|
| L5 LLM judge bất đồng bộ + hiệu chỉnh ngưỡng | Cao |
| Trang admin sửa prompt/metric | Cao — đây là yêu cầu gốc của người đặt bài |
| Free-form SQL + `sqlguard` + self-consistency | Trung bình |
| Xuất CSV phân khúc cho CRM | Trung bình |
| Webhook Zalo | Thấp — ngoài đường găng, xem [12](12-build-deploy.md) §12.8 |
| Biểu đồ waterfall phân rã lợi nhuận | Thấp — đẹp nhưng không thiết yếu |

## 14.2 Rủi ro

Xếp theo tích của khả năng xảy ra và mức tác động.

### R1 — Trần 10 RPM của MaaS làm hỏng buổi demo · Khả năng: cao · Tác động: cao

Trần 10 request/phút tính cho **cả tài khoản**, dùng chung mọi model. Nếu nhiều đội cùng dùng chung tài khoản, hoặc ban giám khảo hỏi liên tiếp, agent sẽ xếp hàng.

*Giảm thiểu, theo thứ tự đã có trong thiết kế:*
1. Ba tab dashboard không gọi LLM — phần lớn màn hình demo không tiêu quota.
2. Token bucket client ở 8 RPM, không bao giờ để đụng trần.
3. Cache câu trả lời theo `hash(câu hỏi + phiên bản prompt + phiên bản dữ liệu)`.
4. Judge chạy bất đồng bộ, không chiếm slot trên đường găng.
5. **Chuẩn bị trước 5 câu hỏi demo và làm ấm cache ngay trước khi trình bày.**

### R2 — Security Group của vDB chặn IP egress của AgentBase · Khả năng: trung bình · Tác động: cao

GreenNode không công bố dải IP egress của Runtime. Nếu siết Security Group quá chặt, agent trên prod không nối được DB.

*Giảm thiểu:* deploy sớm ở Giai đoạn 5 chứ không để đến phút chót. Nếu bị chặn thì chuyển sang đường 2 ở [03](03-database-choice.md) §3.3 (mở `0.0.0.0/0`, bù bằng TLS + mật khẩu mạnh + role chỉ đọc). Dữ liệu là mock nên rủi ro thực tế thấp.

### R3 — Model không tuân thủ ràng buộc "không viết chữ số" · Khả năng: trung bình · Tác động: trung bình

Nếu model yếu, nó sẽ viết thẳng "6,20" thay vì `{{F1.r1.romi}}`, và lớp L2 chặn hàng loạt.

*Giảm thiểu:*
1. Few-shot có phản ví dụ rõ ràng ([07](07-prompt-fewshot.md) §7.2).
2. `temperature` hạ xuống 0,1.
3. Đổi sang model lớn hơn trong danh sách ENABLED.
4. **Chế độ nới có kiểm soát:** cho phép model viết số trực tiếp nhưng L2 vẫn đối chiếu từng con số với ô dữ liệu; số khớp thì `WARN` thay vì `BLOCK`. Chế độ này yếu hơn PCN nhưng vẫn chặn được số bịa — và nó là đường lui, **không phải là tắt L2**.

### R4 — Tên model trong sổ tay không khớp catalog · Khả năng: đã xác nhận · Tác động: thấp

"Qwen 3.5 27B" không có trong catalog MaaS. Hardcode tên này sẽ lỗi 404.

*Giảm thiểu:* chạy `aip.sh models list --status ENABLED` **trước khi viết dòng code nào**, và để `LLM_MODEL` ở biến môi trường chứ không trong code.

### R5 — Dữ liệu chỉ có 31 ngày · Khả năng: chắc chắn · Tác động: trung bình

Không phân tích được xu hướng theo tháng, mùa vụ, hay cohort dài hạn. Câu hỏi "tháng này so tháng trước" là câu hỏi tự nhiên mà agent phải từ chối.

*Giảm thiểu:* biến hạn chế thành điểm cộng — semantic layer chặn tường minh và agent giải thích lý do. Ban giám khảo hỏi câu đó sẽ thấy agent **biết mình không biết**, và đó là một điểm thuyết phục chứ không phải một thiếu sót.

### R6 — `horizon_factor` trong CLV là giả định · Khả năng: chắc chắn · Tác động: trung bình

CLV dự báo phụ thuộc một tham số không suy ra được từ dữ liệu.

*Giảm thiểu:* in giả định kèm mọi con số CLV, để tham số ở config cho người dùng tự chỉnh, và trình bày CLV dưới dạng khoảng chứ không phải điểm.

### R7 — Zalo không tích hợp được cho custom agent · Khả năng: đã xác nhận · Tác động: thấp

Tích hợp Zalo sẵn có chỉ dành cho OpenClaw, không dành cho image tuỳ chỉnh.

*Giảm thiểu:* xếp ngoài đường găng. `/invocations` đã sẵn sàng nếu muốn nối webhook sau.

### R8 — Bí mật nằm trong repo · Khả năng: chắc chắn · Tác động: trung bình

Là lựa chọn có ý thức theo yêu cầu người đặt bài.

*Giảm thiểu:* repo private; gom vào đúng một file; agent chỉ có role chỉ đọc; đổi toàn bộ key và xoá instance ngay sau hackathon; điểm chuyển sang secret manager đã chừa sẵn ở [10](10-config-secrets.md) §10.5.

### R9 — Phân khúc theo luật có thể bỏ sót cấu trúc · Khả năng: trung bình · Tác động: thấp

Luật thủ công có thể không phát hiện một nhóm khách có giá trị mà ta chưa nghĩ tới.

*Giảm thiểu:* chế độ k-means đối chứng (`--mode kmeans`) chạy offline để so sánh. Nếu k-means tìm ra cụm mà luật không có, bổ sung luật — chứ không thay luật bằng k-means, vì luật mới là thứ giải thích được cho kiểm toán.

## 14.3 Câu hỏi mở — cần người đặt bài quyết định

| # | Câu hỏi | Vì sao cần quyết | Mặc định nếu không trả lời |
|---|---|---|---|
| Q1 | ETL chạy tay hay theo lịch? Nếu theo lịch thì tần suất? | Ảnh hưởng tới việc có cần scheduler và cơ chế vô hiệu cache | Chạy tay, có nút trên trang admin |
| Q2 | `horizon_factor` nên là bao nhiêu theo hiểu biết nghiệp vụ? | Ảnh hưởng trực tiếp tới mọi con số CLV dự báo | 1,0 và in rõ giả định |
| Q3 | Có cần Zalo bot không, hay web UI là đủ? | Quyết định ~1 ngày công | Không làm, để ngoài đường găng |
| Q4 | Ngưỡng ROMI nào là "chấp nhận được" theo chính sách công ty? | Dùng để tô màu và sinh cảnh báo tự động | ROMI < 0 đỏ, < 1,0 vàng, ≥ 2,0 xanh |
| Q5 | Danh sách khách hàng xuất ra đi đâu — CSV tải về hay đẩy thẳng sang CRM? | Quyết định có cần vStorage và tích hợp ngoài | CSV tải về |
| Q6 | Có cần đăng nhập/phân quyền không? | Đang là non-goal | Không, PoC một vai trò |
| Q7 | Chi phí thu hút nên tính gồm `partner_fee` không? | Đổi ROMI của hai chiến dịch đối tác một cách đáng kể | Không gồm — `partner_fee` là chi phí vận hành, tính trong `total_cost` |

Q7 đáng bàn nhất. `partner_fee` của Broker chiếm phần lớn khoản lỗ. Nếu xếp nó vào chi phí thu hút thì ROMI của Broker và Momo thay đổi rõ rệt. Thiết kế hiện tại xếp nó vào `total_cost` (nên nó ảnh hưởng tới `net_profit`) nhưng **không** xếp vào `acquisition_spend` (mẫu số của ROMI). Đây là một lựa chọn có thể tranh luận, và vì nó nằm trong `metrics.yml` nên đổi được trong một phút — nhưng phải đổi kèm cập nhật giá trị tham chiếu ở [02](02-data-model.md) §2.4.

## 14.4 Sau PoC

Nếu dự án đi tiếp lên dữ liệu thật, bốn việc **không thể bỏ qua**:

1. **Bảo mật:** chuyển sang VPC mode + Private Endpoint, bí mật vào Access Control của AgentBase, bật Inbound Auth, và thêm RBAC ở tầng ứng dụng.
2. **Dữ liệu cá nhân:** `ip_address`, `income`, `age` là dữ liệu cá nhân. Cần che/băm trong log, kiểm soát ai xuất được danh sách khách hàng, và ghi log mọi lần xuất.
3. **Khoá nối phễu:** đề nghị đội dữ liệu bổ sung `lead_id` vào `fact_loan`. Khi có khoá đó, attribution mức cá thể trở nên khả thi và toàn bộ nhóm chỉ số phễu mạnh lên đáng kể. Đây là đề xuất kỹ thuật có giá trị nghiệp vụ cao nhất từ dự án này.
4. **Lịch sử dài hơn:** cần tối thiểu 12 tháng để mô hình CLV thoát khỏi giả định `horizon_factor`, và để phân tích cohort có ý nghĩa.
