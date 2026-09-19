# 03 — Chọn database: cái gì, cài ở đâu trên GreenNode

> **Kết luận ngắn:** dùng **vDB RDS — PostgreSQL Standalone** của VNG Cloud/GreenNode, bật **Public Endpoint**, siết Security Group, và cả máy local lẫn agent chạy trên AgentBase đều nối tới đúng instance đó bằng một biến `DATABASE_URL` duy nhất.

## 3.1 Yêu cầu ràng buộc

| # | Yêu cầu | Nguồn |
|---|---|---|
| R1 | Local và Prod đọc **chung một DB** | Yêu cầu người đặt bài |
| R2 | DB phải được **cài hoặc sử dụng trên GreenNode** | Yêu cầu người đặt bài |
| R3 | Agent chạy trên AgentBase phải nối được tới DB | Kiến trúc |
| R4 | Phải chịu được truy vấn phân tích ad-hoc do LLM sinh ra | [05](05-semantic-layer.md) |
| R5 | Phải có vai trò **chỉ đọc** để rào SQL sinh bởi LLM | [08](08-anti-hallucination.md) |
| R6 | Lưu được telemetry của agent (ghi) | [13](13-testing-eval.md) |

Một ràng buộc kỹ thuật quyết định, xác nhận từ tài liệu GreenNode: **filesystem của container AgentBase Runtime là ephemeral** — mọi thứ ghi trong container mất khi replica restart, scale hoặc deploy version mới. Vì vậy **không thể** dùng SQLite/DuckDB file nằm trong image làm nguồn dữ liệu có ghi. Dữ liệu bắt buộc phải nằm ngoài container.

## 3.2 So sánh phương án

| Phương án | Đáp R1 | Đáp R2 | Ưu | Nhược | Kết luận |
|---|---|---|---|---|---|
| **A. vDB RDS PostgreSQL Standalone** | ✅ | ✅ dịch vụ quản lý của GreenNode | Managed, có backup/restore, public + private endpoint, security group, đúng chuẩn SQL phân tích, có `EXPLAIN`, có role phân quyền, extension phong phú | Tốn credit; public endpoint cần siết IP | ✅ **Chọn** |
| B. PostgreSQL trong Docker trên vServer VM (GreenNode) | ✅ | ✅ tự cài trên hạ tầng GreenNode | Toàn quyền, rẻ nhất, cài `pgvector` tuỳ ý, dựng trong 10 phút | Tự lo backup, tự lo TLS, tự vá bảo mật | ⚠️ **Phương án dự phòng** — dùng nếu quota vDB không được cấp |
| C. DuckDB file trên vStorage (S3) | ⚠️ đọc chung được, ghi thì không | ✅ vStorage là dịch vụ GreenNode | Cực nhẹ, phân tích rất nhanh, không tốn tiền DB | Không ghi đồng thời; telemetry phải đẩy sang chỗ khác; không có role chỉ đọc mức DB | ❌ Không đủ cho R5/R6 |
| D. MySQL / MariaDB (vDB RDS) | ✅ | ✅ | Có sẵn | Yếu hơn Postgres ở window function, `FILTER`, CTE, `EXPLAIN` phân tích | ❌ Không có lý do chọn |
| E. Neon / Supabase / RDS AWS | ✅ | ❌ | Tiện | **Vi phạm R2** | ❌ Loại |

### Vì sao PostgreSQL chứ không phải kho phân tích chuyên dụng

Tổng dữ liệu là **24 297 dòng** trên 6 bảng — khoảng vài MB. Mọi truy vấn trong tài liệu này chạy dưới 50 ms trên một instance PostgreSQL nhỏ nhất. ClickHouse, BigQuery hay Snowflake là đem dao mổ trâu giết gà, và còn làm hỏng yêu cầu "một DB dùng chung, cài trên GreenNode".

Những gì PostgreSQL cho ta mà bộ dữ liệu này thật sự cần:

* `COUNT(*) FILTER (WHERE ...)` — dùng dày đặc trong các mart phễu.
* `FULL OUTER JOIN` — cần cho `mart_campaign_daily` vì lead và application đếm độc lập.
* **`EXPLAIN` không thực thi** — là lớp L1 trong hàng rào chống hallucination: kiểm tra SQL do LLM sinh trước khi cho chạy.
* **Role và `GRANT` mức cột/bảng** — cho phép cấp một vai trò chỉ đọc thật sự, không phải chỉ là quy ước trong code.
* **`statement_timeout` mức role** — chặn truy vấn chạy loạn.
* `pgvector` (tuỳ chọn) — nếu sau này cần RAG trên tài liệu định nghĩa chỉ số.

## 3.3 Thiết kế triển khai

```
                    GreenNode Cloud
  +--------------------------------------------------+
  |                                                  |
  |  vDB RDS - PostgreSQL Standalone                 |
  |  instance: msb-mkt-insight-poc                   |
  |  db: mkt_insight                                 |
  |  schemas: raw / mart / ops                       |
  |                                                  |
  |  Public Endpoint  <hostname>:5432   (bat)        |
  |  Private Endpoint <ip trong subnet> (khong dung) |
  |  Security Group: chi cho phep CIDR da khai bao   |
  +------------------+-------------------------------+
                     |
       +-------------+--------------+
       |                            |
  [ May dev local ]           [ AgentBase Runtime ]
  APP_PROFILE=local           APP_PROFILE=greennode
  DATABASE_URL=...            DATABASE_URL=...
  (cung mot instance, khac model LLM)
```

Agent trên AgentBase chạy ở **network mode PUBLIC** (mặc định). Mode này có egress internet — điều này được xác nhận gián tiếp nhưng chắc chắn, vì chính tài liệu AgentBase hướng dẫn agent gọi `https://hcm04.vstorage.vngcloud.vn` bằng boto3 và gọi MaaS API qua internet. Mode VPC (để đi vào Private Endpoint) đòi **VPC Peering phải mở ticket với GreenNode support trước** — không khả thi trong thời gian hackathon, nên ta đi Public Endpoint.

### Cấu hình instance đề xuất

| Tham số | Giá trị | Lý do |
|---|---|---|
| Engine | PostgreSQL Standalone, bản mới nhất có sẵn (≥15) | Không cần HA cho PoC |
| Flavor | Nhỏ nhất (1–2 vCPU / 2–4 GB) | 24k dòng |
| Storage | 20 GB | Thừa sức |
| Public Endpoint | **Bật** | Bắt buộc để local nối chung (R1) |
| Backup | Bật, giữ 7 ngày | Rẻ, cứu được khi ETL chạy nhầm |
| DB name | `mkt_insight` | |

### Bảo mật — và một rủi ro phải nói thẳng

vDB RDS mặc định **chấp nhận kết nối từ mọi nơi (`0.0.0.0/0`)**. Phải siết lại ngay sau khi tạo.

Vấn đề thực tế: GreenNode **không công bố dải IP egress của AgentBase Runtime**. Vì vậy có hai đường đi:

**Đường 1 — siết chặt, thử trước (nên làm):**
1. Thêm CIDR của máy dev (IP public của bạn, `/32`).
2. Deploy agent, gọi thử, xem log. Nếu kết nối được thì đã có IP; nếu bị chặn thì chuyển đường 2.

**Đường 2 — mở rộng, bù bằng lớp khác (thực tế cho hackathon):**
Nếu không xác định được IP egress, để `0.0.0.0/0` nhưng bù lại bằng bốn lớp:
1. Mật khẩu ngẫu nhiên ≥32 ký tự cho mọi role.
2. **Bắt buộc TLS**: chuỗi kết nối có `sslmode=require`.
3. **Agent dùng role chỉ đọc** — kể cả bị lộ thông tin kết nối, kẻ tấn công không sửa/xoá được dữ liệu.
4. Đổi toàn bộ mật khẩu và **xoá instance ngay sau hackathon**. Dữ liệu là mock nên thiệt hại tối đa là lộ dữ liệu giả.

> Đây là đánh đổi có ý thức, hợp với phạm vi PoC và với yêu cầu "tạm thời lưu key trong repo". Nếu sau này đưa lên dữ liệu thật thì phải chuyển sang VPC mode + Private Endpoint + Access Control của AgentBase, và đây là việc **không thể bỏ qua**.

### Phân quyền vai trò — đây là rào chắn thật, không phải hình thức

```sql
-- 1) Chu so huu: chay ETL, tao bang
CREATE ROLE mkt_owner LOGIN PASSWORD '<random-32+>';
GRANT ALL ON SCHEMA raw, mart, ops TO mkt_owner;

-- 2) Vai tro AGENT dung de chay SQL do LLM sinh: CHI DOC, va chi o mart
CREATE ROLE mkt_agent_ro LOGIN PASSWORD '<random-32+>';
REVOKE ALL ON SCHEMA public FROM mkt_agent_ro;
REVOKE ALL ON SCHEMA raw    FROM mkt_agent_ro;   -- agent khong duoc cham schema raw
GRANT USAGE ON SCHEMA mart TO mkt_agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO mkt_agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO mkt_agent_ro;

-- Chan truy van chay loan va chan ghi o muc DB, khong phu thuoc vao code
ALTER ROLE mkt_agent_ro SET statement_timeout        = '15s';
ALTER ROLE mkt_agent_ro SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE mkt_agent_ro SET default_transaction_read_only = on;
ALTER ROLE mkt_agent_ro SET search_path = 'mart';
ALTER ROLE mkt_agent_ro SET work_mem = '32MB';

-- 3) Vai tro ghi telemetry: chi INSERT vao ops
CREATE ROLE mkt_trace_rw LOGIN PASSWORD '<random-32+>';
GRANT USAGE ON SCHEMA ops TO mkt_trace_rw;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA ops TO mkt_trace_rw;
```

Ba kết nối tách biệt trong ứng dụng, không dùng chung pool:

| Pool | Role | Dùng ở đâu |
|---|---|---|
| `engine_ro` | `mkt_agent_ro` | Mọi truy vấn phục vụ câu trả lời — metric tool và SQL tool |
| `engine_trace` | `mkt_trace_rw` | Ghi `ops.agent_trace` |
| `engine_admin` | `mkt_owner` | **Chỉ** trong script ETL, không bao giờ nằm trong process phục vụ web |

`default_transaction_read_only = on` đặt ở mức role có nghĩa là: kể cả khi toàn bộ lớp kiểm tra SQL trong code bị bỏ qua vì một lỗi lập trình, một câu `DELETE` vẫn bị chính PostgreSQL từ chối. Đó là khác biệt giữa một rào chắn và một lời hứa.

## 3.4 Bảng telemetry (schema `ops`)

```sql
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE ops.etl_run (
    run_id        BIGSERIAL PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    source        TEXT NOT NULL,            -- excel | parquet
    status        TEXT NOT NULL,            -- RUNNING | OK | FAILED
    rows_loaded   JSONB,                    -- {"fact_lead": 14530, ...}
    error_message TEXT
);

CREATE TABLE ops.dq_result (
    run_id      BIGINT REFERENCES ops.etl_run(run_id),
    check_id    TEXT NOT NULL,              -- DQ-01 | INV-3 ...
    severity    TEXT NOT NULL,              -- INFO | WARN | BLOCK
    passed      BOOLEAN NOT NULL,
    observed    JSONB,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, check_id)
);

-- Chi tiet cac cot xem 08-anti-hallucination.md muc 7
CREATE TABLE ops.agent_trace (
    trace_id     UUID PRIMARY KEY,
    session_id   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    question     TEXT NOT NULL,
    playbook     TEXT,
    evidence     JSONB,        -- danh sach query da chay + fingerprint ket qua
    answer_md    TEXT,
    checks       JSONB,        -- ket qua tung lop kiem tra
    trust_score  NUMERIC(4,3),
    decision     TEXT,         -- ANSWERED | HEDGED | ABSTAINED | BLOCKED
    block_reason TEXT,
    prompt_version TEXT NOT NULL,
    model_name     TEXT NOT NULL,
    profile        TEXT NOT NULL,   -- local | greennode
    latency_ms   INTEGER,
    tokens_in    INTEGER,
    tokens_out   INTEGER
);
CREATE INDEX ix_trace_created  ON ops.agent_trace (created_at DESC);
CREATE INDEX ix_trace_decision ON ops.agent_trace (decision);
```

Ba cột `prompt_version`, `model_name`, `profile` là bắt buộc. Không có chúng thì khi chất lượng câu trả lời tụt, không ai truy được là do sửa prompt, do đổi model, hay do dữ liệu đổi.

## 3.5 Mirror local tuỳ chọn (không phải DB thứ hai)

Yêu cầu là một DB dùng chung, và thiết kế trên đáp ứng đúng như vậy. Nhưng khi mất mạng hoặc khi chạy test trong CI, cần một bản sao chạy được ngoại tuyến. Giải pháp: **một file `docker-compose.dev.yml` dựng PostgreSQL trên máy** với cùng schema, dùng **chỉ** cho unit test và golden set.

Quy tắc rõ ràng để không sinh ra "hai nguồn sự thật":

* Mirror local **không bao giờ** được dùng để trả lời người dùng thật hay để demo.
* Nó được tạo bằng chính `etl/` từ cùng file Excel, nên schema luôn đồng nhất.
* `APP_PROFILE=test` mới trỏ vào nó. `local` và `greennode` đều trỏ tới vDB RDS.

```yaml
# docker-compose.dev.yml  -- chi dung cho test/CI
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: mkt_insight
      POSTGRES_USER: mkt_owner
      POSTGRES_PASSWORD: devonly
    ports: ["55432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
volumes: { pgdata: {} }
```

## 3.6 vStorage (S3) — dùng cho file, không dùng cho dữ liệu

GreenNode có **vStorage**, tương thích S3, endpoint dạng `https://hcm04.vstorage.vngcloud.vn` (region `HCM04`; còn có `han02`/`HAN02`), ký bằng AWS Signature V4, truy cập qua `boto3`. Khoá S3 tạo ở vIAM console.

Trong kiến trúc này vStorage giữ đúng một vai trò: **nơi chứa file xuất ra**, vì filesystem container là ephemeral.

| Dùng vStorage cho | Không dùng vStorage cho |
|---|---|
| File CSV danh sách khách hàng mục tiêu mà agent xuất cho CRM | Dữ liệu phân tích — đó là việc của PostgreSQL |
| Bản chụp báo cáo PDF/HTML | Telemetry |
| File Excel nguồn để ETL chạy trên cloud | State hội thoại |

Ở giai đoạn PoC, tính năng xuất CSV có thể trả file trực tiếp qua HTTP response mà chưa cần vStorage. Đưa vStorage vào ngay từ đầu chỉ làm rối. Để ở [14-roadmap-risks.md](14-roadmap-risks.md) như mục Phase 2.

## 3.7 Các bước dựng, theo thứ tự

1. Console vDB → tạo RDS PostgreSQL Standalone, flavor nhỏ nhất, DB `mkt_insight`.
2. Tab **Connectivity & Security** → bật Public Endpoint → ghi lại hostname và port (endpoint là giá trị cụ thể của instance, không theo mẫu URL nào — phải đọc từ console).
3. **Security Group Rules** → xoá `0.0.0.0/0`, thêm `<IP public máy dev>/32`. Xem §3.3 nếu cần mở lại.
4. Nối bằng `psql`, chạy `sql/00_roles.sql` (khối GRANT ở §3.3).
5. `python -m etl.load_excel --source excel` → `python -m etl.build_marts` → `python -m etl.dq_checks`.
6. Kiểm tra: `SELECT * FROM ops.dq_result WHERE NOT passed;` phải không có dòng `BLOCK` nào.
7. Đưa `DATABASE_URL` vào `config/secrets.yaml` (xem [10](10-config-secrets.md)) và vào `environmentVariables` của AgentBase Runtime.

Chuỗi kết nối chuẩn dùng ở cả hai môi trường:

```
postgresql+psycopg://mkt_agent_ro:<password>@<rds-host>:5432/mkt_insight?sslmode=require
```
