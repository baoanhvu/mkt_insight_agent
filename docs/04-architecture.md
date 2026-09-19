# 04 — Kiến trúc tổng thể

## 4.1 Bối cảnh (C4 — Level 1)

```
   +-------------------+          +--------------------------+
   | Marketing Lead    |          | CRM / Segment Manager    |
   | Head of Lending   |          |                          |
   +---------+---------+          +------------+-------------+
             |  trinh duyet web                |
             +----------------+----------------+
                              v
              +-------------------------------+
              |   Marketing Insight Agent     |
              |   (FastAPI, 1 container)      |
              +----+---------------------+----+
                   |                     |
       SQL chi doc |                     | HTTPS, OpenAI-compatible
                   v                     v
     +----------------------+   +--------------------------+
     | GreenNode vDB RDS    |   | GreenNode MaaS           |
     | PostgreSQL           |   | /v1/chat/completions     |
     | raw / mart / ops     |   | 10 RPM, 14.400 req/ngay  |
     +----------+-----------+   +--------------------------+
                ^
                | ETL chay tay hoac theo lich
      +---------+----------+
      | data/*.xlsx        |
      | data/parquet/      |
      +--------------------+
```

Hai hệ thống ngoài, và mỗi cái áp một ràng buộc cứng lên kiến trúc:

* **vDB RDS PostgreSQL** — nguồn sự thật duy nhất. Agent nối bằng role chỉ đọc.
* **GreenNode MaaS** — **giới hạn 10 request/phút và 14 400 request/ngày cho cả tài khoản**, dùng chung mọi model. Đây là ràng buộc định hình toàn bộ thiết kế agent (xem §4.5).

## 4.2 Container (C4 — Level 2)

Toàn bộ nằm trong **một container duy nhất**, vì AgentBase Runtime triển khai đúng một image và yêu cầu nó lắng nghe cổng 8080 với `GET /health` trả 200. Tách microservice ở PoC này chỉ làm tăng bề mặt lỗi mà không đổi lại được gì.

```
+--------------------------------------------------------------------+
|  Container : lang nghe 0.0.0.0:8080                                 |
|                                                                     |
|  +--------------------------------------------------------------+   |
|  | Web Layer (FastAPI)                                           |  |
|  |  GET  /health            <- BAT BUOC boi AgentBase            |  |
|  |  POST /invocations       <- quy uoc AgentBase (goi tu Zalo/API)|  |
|  |  GET  /                  <- UI: dashboard + chat              |  |
|  |  GET  /api/dashboard/*   <- so lieu cho bieu do               |  |
|  |  POST /api/chat (SSE)    <- hoi dap streaming                 |  |
|  |  GET|PUT /api/admin/*    <- sua prompt / metric / nguong       |  |
|  +-------------------------------+------------------------------+   |
|                                  |                                  |
|  +-------------------------------v------------------------------+   |
|  | Agent Orchestrator                                            |  |
|  |  Router -> Playbook -> Planner -> Tools -> Narrator -> Verify |  |
|  +----+------------------+---------------------+----------------+   |
|       |                  |                     |                    |
|  +----v-------+   +------v---------+   +-------v--------------+     |
|  | Semantic   |   | Analytics      |   | Verification         |     |
|  | Layer      |   | (CLV, phan     |   | Pipeline (L0..L6)    |     |
|  | metrics.yml|   |  khuc, thong ke)|  |                      |     |
|  +----+-------+   +------+---------+   +-------+--------------+     |
|       |                  |                     |                    |
|  +----v------------------v---------------------v--------------+     |
|  | Data Access : 3 pool tach biet theo role                    |    |
|  |   engine_ro (mkt_agent_ro) | engine_trace | engine_admin    |    |
|  +--------------------------+---------------------------------+    |
|                             |                                       |
|  +--------------------------v---------------------------------+    |
|  | LLM Client : OpenAI-compatible, co retry/backoff/rate-limit |    |
|  +------------------------------------------------------------+    |
|                                                                     |
|  Config: config/*.yaml + prompts/*.yaml  (hot-reload, co version)   |
+--------------------------------------------------------------------+
```

## 4.3 Tech stack và lý do chọn

| Lớp | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3.13 | Dockerfile mẫu của AgentBase dùng `python:3.13-slim` |
| Web | **FastAPI** + Uvicorn | Async, có SSE, tự sinh OpenAPI, một process phục vụ cả UI lẫn API |
| Template | Jinja2 | Có sẵn trong FastAPI, không cần bước build JS |
| CSS | **Tailwind CSS** (CDN play script) | Thư viện có sẵn, ràng buộc chat 60% viết bằng một class |
| JS tương tác | **Alpine.js** (CDN) | ~15 KB, đủ cho tab/state/stream; không cần bundler |
| Biểu đồ | **Apache ECharts** (CDN) | Mạnh hơn Chart.js ở biểu đồ phễu và sankey — đúng thứ ta cần |
| Markdown | `marked` (CDN) | Render câu trả lời của agent |
| DB driver | SQLAlchemy 2.x Core + `psycopg[binary]` | Core chứ không ORM: ta viết SQL thật, chỉ cần pool + bind param |
| Phân tích SQL | **`sqlglot`** | Parse SQL do LLM sinh thành AST để kiểm tra — xem [08](08-anti-hallucination.md) L0 |
| Thống kê | `scipy.stats` + `statsmodels` (nhẹ) | z-test hai tỷ lệ, khoảng tin cậy Wilson, bootstrap |
| Cấu hình | `pydantic-settings` + `PyYAML` | Validate cấu hình lúc khởi động, fail-fast |
| LLM | `openai` SDK trỏ `base_url` MaaS | MaaS là OpenAI-compatible |
| Test | `pytest` + `testcontainers` (tuỳ chọn) | Golden set chạy trên DB đóng băng |

Không dùng LangChain hay LangGraph. Tài liệu của chính AgentBase nói rõ framework "Custom" được hỗ trợ đầy đủ. Luồng agent ở đây là một máy trạng thái tuyến tính, ngắn, và mọi bước đều phải kiểm tra được — thêm một lớp trừu tượng vào giữa chỉ làm việc truy vết lỗi khó hơn mà không giải quyết vấn đề nào ta đang có.

## 4.4 Luồng xử lý một câu hỏi

```
Nguoi dung: "Vi sao Broker Network lo?"
    |
 1. Router (LLM, 1 goi)  -> intent = CAMPAIGN_DIAGNOSIS, entities = [CMP-PTN-BRK01]
    |                        (cache theo chuan hoa cau hoi)
 2. Playbook campaign_diagnosis: danh sach MetricRequest co san, KHONG do LLM che
    |     m_campaign_pnl_breakdown(campaign_id=CMP-PTN-BRK01)
    |     m_campaign_funnel(campaign_id=CMP-PTN-BRK01)
    |     m_campaign_benchmark(exclude_product=PRD-RL)
    |
 3. Semantic Layer compile -> SQL tham so hoa (KHONG noi chuoi)
    |
 4. engine_ro thuc thi  -> EvidenceSet
    |     F1 = bang phan ra chi phi   (12 dong x 4 cot)
    |     F2 = bang phieu             (1 dong x 6 cot)
    |     F3 = benchmark cac chien dich khac (5 dong)
    |     moi o co dia chi: F1.r3.partner_fee = 168974100
    |
 5. Stats guard: moi so sanh sinh ra deu kem n, CI, p-value
    |
 6. Narrator (LLM, 1 goi): nhan EvidenceSet dang JSON + prompt tu file
    |     Bat buoc xuat so duoi dang the: {{F1.r3.partner_fee}}
    |     LLM chi viet CHU, khong viet SO
    |
 7. Verification Pipeline L0..L6
    |     L2 numeric grounding -> the nao khong phan giai duoc = FAIL
    |     L3 entity grounding
    |     L4 stats guard
    |     L5 LLM judge (chi khi can, xem 4.5)
    |     -> TrustScore + decision
    |
 8. Renderer thay the -> so that, dinh dang vi-VN, gan nhan "da kiem chung"
    |
 9. Tra ve: cau tra loi + Trust badge + nut "Xem SQL & du lieu"
10. Ghi ops.agent_trace
```

Điểm mấu chốt ở bước 6: LLM nhận evidence và trả về văn bản có **thẻ** thay cho số. Nếu nó cố viết một con số trực tiếp, bước 7 bắt được ngay vì con số đó không phải thẻ. Nếu nó bịa một `fact_id` không tồn tại, bước 8 không phân giải được và câu trả lời bị chặn. Đây là ý tưởng **Proof-Carrying Numbers** — đẩy việc xác minh xuống tầng render và mặc định fail-closed. Chi tiết ở [08](08-anti-hallucination.md) §3.

## 4.5 Ràng buộc 10 RPM định hình kiến trúc như thế nào

Tài khoản MaaS bị giới hạn **10 request/phút toàn tài khoản**. Nếu một câu hỏi tốn 4 lượt gọi LLM thì hệ thống chỉ phục vụ được 2,5 câu hỏi/phút — không thể demo trước ban giám khảo, và càng không thể có nhiều người dùng cùng lúc.

Kiến trúc phải tiết kiệm token-call như một tài nguyên khan hiếm:

| Quyết định | Tiết kiệm | Đánh đổi |
|---|---|---|
| **Dashboard hoàn toàn không gọi LLM.** D1 là SQL + biểu đồ, phần chữ dùng template có chỗ trống điền số | 0 gọi cho màn hình hay dùng nhất | Văn phong cố định — chấp nhận được, thậm chí tốt hơn cho báo cáo định kỳ |
| **Playbook thay vì để LLM lập kế hoạch tự do.** Danh sách chỉ số cho mỗi intent là cố định trong YAML | Bỏ hẳn 1–2 lượt gọi "suy nghĩ" | Kém linh hoạt với câu hỏi lạ — có đường thoát là free-form SQL tool |
| **Router và Narrator gộp khi có thể.** Câu hỏi khớp playbook rõ ràng thì bỏ qua router | −1 lượt | |
| **LLM-judge chạy bất đồng bộ, không chặn.** Trả lời trước, huy hiệu Trust cập nhật sau qua SSE | Người dùng không phải chờ | Trong khoảng ngắn, câu trả lời hiển thị chưa có điểm judge — bù bằng việc các lớp tất định đã chạy xong và chúng mới là lớp chính |
| **Cache theo `hash(câu hỏi chuẩn hoá + phiên bản prompt + phiên bản dữ liệu)`** | Câu hỏi lặp lại tốn 0 lượt | Cần vô hiệu cache khi ETL chạy lại |
| **Token bucket phía client, 8 req/phút** | Không bao giờ bị 429 | Xếp hàng khi cao điểm |
| **Self-consistency k=3 chỉ bật cho free-form SQL** | Không tiêu k lượt cho đường đi thường | Đường free-form chậm hơn, đúng như mong muốn |

Ngân sách mục tiêu: **≤ 2 lượt gọi LLM cho một câu hỏi chat**, **0 lượt cho dashboard**. Như vậy ở 8 req/phút phục vụ được 4 câu hỏi/phút — đủ cho demo và cho vài người dùng đồng thời.

Đây cũng là một lập luận thiết kế đẹp cần nói trước ban giám khảo: *việc đẩy tính toán xuống SQL tất định không chỉ chống hallucination, nó còn làm hệ thống chạy được dưới trần rate limit.* Hai mục tiêu trùng nhau.

## 4.6 Mô hình trạng thái

AgentBase yêu cầu container **stateless** vì có thể scale nhiều replica và filesystem là ephemeral.

| Trạng thái | Nơi lưu | Ghi chú |
|---|---|---|
| Lịch sử hội thoại | Client gửi kèm mỗi request; đồng thời ghi `ops.agent_trace` | Không giữ trong RAM process |
| Cache kết quả metric | `cachetools.TTLCache` trong process, TTL 300s | Chỉ là tối ưu; mất cache không sai kết quả |
| Cache câu trả lời LLM | Bảng `ops.answer_cache` trong Postgres | Dùng chung giữa các replica |
| Prompt / config | File trong image + hot-reload từ đĩa | Sửa qua trang admin thì ghi xuống DB rồi các replica đọc lại — xem [07](07-prompt-fewshot.md) §6 |
| Session id | Header `X-GreenNode-AgentBase-Session-Id` | AgentBase truyền vào |

## 4.7 Xử lý lỗi và suy giảm có kiểm soát

| Hỏng ở đâu | Hành vi | Người dùng thấy gì |
|---|---|---|
| DB không nối được | `/health` vẫn 200 (để runtime không bị kill), `/readyz` trả 503 | Banner "Đang mất kết nối dữ liệu", dashboard hiện dữ liệu cache cuối |
| DQ có lỗi mức BLOCK | Agent từ chối trả lời câu hỏi phân tích | "Dữ liệu chưa qua kiểm tra chất lượng (DQ-08). Không trả lời để tránh sai số." |
| MaaS trả 429 | Backoff mũ, tối đa 3 lần, rồi xếp hàng | "Đang chờ lượt, khoảng Ns" |
| MaaS chết hẳn | Chuyển sang **chế độ template**: dashboard và số liệu vẫn chạy, phần diễn giải dùng văn bản mẫu | Vẫn có số, phần bình luận gọn hơn |
| Verification chặn câu trả lời | Thử sinh lại 1 lần với ràng buộc chặt hơn; vẫn fail thì abstain | "Không đủ cơ sở dữ liệu để kết luận. Đây là số liệu thô: ..." |
| SQL free-form sai sau 3 lần sửa | Dừng vòng lặp | "Không dựng được truy vấn cho câu hỏi này. Thử diễn đạt lại?" |

Nguyên tắc: **hỏng phần diễn giải không được làm hỏng phần số liệu.** Số liệu đến từ SQL, và SQL không cần LLM.

## 4.8 Hiệu năng mục tiêu

| Chỉ số | Mục tiêu | Ghi chú |
|---|---|---|
| Dashboard tải lần đầu | < 1,5 s | 0 lượt LLM, truy vấn dưới 50 ms trên 24k dòng |
| Chat — thời gian tới token đầu | < 2,5 s | 1 lượt narrator, streaming |
| Chat — hoàn tất | < 8 s | Bao gồm kiểm chứng tất định |
| Lớp kiểm tra tất định L0–L4 | < 50 ms | Regex, so khớp, thống kê |
| LLM judge (L5) | bất đồng bộ | Không nằm trên đường găng |
| Bộ nhớ container | < 512 MB | Vừa flavor nhỏ nhất `1x1-general` |

## 4.9 Ranh giới module

```
app/api        -> chi biet HTTP. Khong co logic nghiep vu.
app/agent      -> dan dat luong. Khong viet SQL, khong goi DB truc tiep.
app/semantic   -> so huu dinh nghia chi so. Sinh SQL. Khong goi LLM.
app/data       -> so huu ket noi. Thuc thi SQL. Khong biet gi ve chi so.
app/analytics  -> toan hoc thuan tuy (CLV, phan khuc, thong ke). Khong I/O.
app/verify     -> nhan (answer, evidence) -> tra ve ket qua kiem tra. Thuan ham.
app/llm        -> goi model. Khong biet gi ve nghiep vu.
app/prompts    -> nap va render prompt. Khong goi model.
```

Quy tắc phụ thuộc, kiểm tra được bằng `import-linter` trong CI:

* `analytics` và `verify` **không được import** `data`, `llm`, `api`. Chúng là hàm thuần, nhờ vậy test được mà không cần DB hay mạng.
* `semantic` không được import `llm`. Định nghĩa chỉ số không bao giờ phụ thuộc vào model.
* Chỉ `agent` được phép điều phối nhiều module.
