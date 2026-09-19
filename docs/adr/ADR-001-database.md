# ADR-001 — Chọn PostgreSQL trên vDB RDS của GreenNode

**Trạng thái:** Đã chốt · **Ngày:** 2026-09-19 · Liên quan: [03](../03-database-choice.md)

## Bối cảnh

Yêu cầu: local và prod dùng chung một DB; DB phải được cài hoặc sử dụng trên GreenNode. Dữ liệu là 24 297 dòng trên 6 bảng. Agent cần chạy truy vấn phân tích và cần một vai trò chỉ đọc thật sự để rào SQL do LLM sinh. Hệ thống cũng cần ghi telemetry.

Một ràng buộc kỹ thuật xác nhận từ tài liệu AgentBase: **filesystem container là ephemeral** — mọi thứ ghi bên trong mất khi replica restart hoặc deploy version mới.

## Quyết định

Dùng **vDB RDS — PostgreSQL Standalone**, bật Public Endpoint, siết Security Group. Cả máy dev lẫn AgentBase Runtime nối tới cùng instance qua một `DATABASE_URL`.

## Lý do

* Ephemeral filesystem loại bỏ mọi phương án đặt dữ liệu trong container.
* PostgreSQL cho ba thứ mà thiết kế chống hallucination cần ở mức DB chứ không phải mức code: **role chỉ đọc**, **`statement_timeout`**, và **`EXPLAIN` không thực thi**.
* Cú pháp cần dùng dày đặc — `COUNT(*) FILTER`, `FULL OUTER JOIN` — có sẵn và tự nhiên trong Postgres.
* Quy mô dữ liệu quá nhỏ để cần kho phân tích chuyên dụng; ClickHouse hay BigQuery vừa thừa vừa vi phạm ràng buộc "trên GreenNode".
* `default_transaction_read_only` đặt ở mức role biến rào chắn thành thứ mà một lỗi lập trình không thể vô hiệu hoá.

## Phương án đã cân nhắc

| Phương án | Vì sao loại |
|---|---|
| PostgreSQL Docker trên vServer VM | Giữ làm **dự phòng** nếu không được cấp quota vDB. Tự lo backup, TLS, vá lỗi |
| DuckDB trên vStorage S3 | Không ghi đồng thời được; không có role mức DB; telemetry phải đi nơi khác |
| MySQL / MariaDB (cũng có trên vDB) | Yếu hơn ở window function, `FILTER`, CTE. Không có lý do chọn |
| Neon / Supabase | Vi phạm ràng buộc "DB trên GreenNode" |

## Hệ quả

**Tích cực:** một nguồn sự thật; số local và prod luôn trùng khít theo thiết kế; rào chỉ đọc là thật; có backup.

**Tiêu cực:** Public Endpoint là bề mặt tấn công. GreenNode không công bố dải IP egress của Runtime nên có thể phải mở `0.0.0.0/0` — được bù bằng TLS, mật khẩu mạnh, role chỉ đọc, và việc xoá instance sau hackathon. Với dữ liệu mock, đánh đổi này chấp nhận được; với dữ liệu thật thì **không**, và khi đó phải chuyển sang VPC mode + Private Endpoint.

**Phụ thuộc:** cần mạng để chạy local. Có `docker-compose.dev.yml` làm mirror **chỉ cho test/CI**, không bao giờ dùng để trả lời người dùng.
