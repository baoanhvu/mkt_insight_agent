# 02 — Mô hình dữ liệu

> Toàn bộ số liệu trong tài liệu này được đo trực tiếp từ `data/full_schema_mock_v2.xlsx` ngày 2026-09-19, không phải ước lượng.

## 2.1 Kết quả profiling dữ liệu nguồn

File Excel có 6 sheet, mỗi sheet là một bảng. Thư mục `data/parquet/` đã có sẵn bản xuất parquet tương ứng (tên cột đã chuẩn hoá snake_case, `dim_customer` partition theo `occupation`).

| Sheet | Số dòng | Grain (1 dòng = ?) | Khoá |
|---|---:|---|---|
| `fact_lead` | 14 530 | 1 lead marketing | `lead_id` |
| `fact_loan` | 2 687 | 1 hồ sơ vay (application) | `application_id` |
| `fact_reject` | 1 062 | 1 hồ sơ bị từ chối | `loan_application_id` |
| `loan_application_pnl` | 2 687 | 1 hồ sơ vay — P&L | `loan_application_id` |
| `fact_digital_footprint` | 2 687 | 1 hồ sơ vay — dấu vết số | `loan_application_id` |
| `dim_customer` | 2 901 | 1 khách hàng | `customer_id` |

### Quan hệ đã kiểm chứng

```
dim_customer (2 901)
     | 1
     | N   <- 100% customer_id trong fact_loan ton tai trong dim_customer
fact_loan (2 687 application, 2 554 khach hang phan biet)
     |-- 1:1    loan_application_pnl       (tap application_id TRUNG KHOP HOAN TOAN)
     |-- 1:1    fact_digital_footprint     (tap application_id TRUNG KHOP HOAN TOAN)
     |-- 1:0..1 fact_reject                (1 062/2 687 - 100% la tap con)

fact_lead (14 530)   X  KHONG co khoa ngoai toi fact_loan
```

### Phát hiện quan trọng nhất: phễu bị đứt ở giữa

`fact_loan` **không có** `lead_id` và **không có** `campaign_id`. Không thể nối một hồ sơ vay về đúng một lead đã sinh ra nó.

Cầu nối duy nhất là bộ `(channel, sub_channel, partner_code)`. May mắn là trong bộ dữ liệu này **`sub_channel` là khoá duy nhất xác định chiến dịch** — đã kiểm chứng: 6 giá trị `sub_channel` ↔ 6 `campaign_id`, ánh xạ 1-1:

| campaign_id | campaign_name | channel | sub_channel | partner_code | product |
|---|---|---|---|---|---|
| CMP-FB-001 | Vay Tieu Dung - Digital Q3 | Facebook Ads | FB_Feed_Ads | DIRECT | PRD-FL |
| CMP-GG-001 | Vay Tin Chap - Google Search | Google Ads | Search_Brand | DIRECT | PRD-FL |
| CMP-TT-001 | Vay Mua Sam - TikTok Awareness | TikTok Ads | InFeed_Video | DIRECT | PRD-FL |
| CMP-ZL-RL1 | Vay Lai - Zalo Remarketing | Zalo Ads | ZNS_Remarketing | DIRECT | PRD-RL |
| CMP-PTN-MOMO | Vay Tieu Dung - Momo Widget | Partner App | Momo_Loan_Widget | PTN-MOMO | PRD-FL |
| CMP-PTN-BRK01 | Vay Tieu Dung - Broker Network | Broker Network | CTV_Referral | PTN-BROKER01 | PRD-FL |

**Hệ quả thiết kế:**

1. Dựng một dimension suy ra: `dim_campaign`, khoá tự nhiên là `sub_channel`.
2. Tỷ lệ chuyển đổi lead → application là **tỷ lệ mức tổng hợp (aggregate)**, KHÔNG phải attribution mức cá thể. Điều này phải ghi vào metadata của chỉ số và phải xuất hiện trong câu trả lời của agent dưới dạng chú thích. Đây chính xác là loại giả định mà một LLM không được rào sẽ lặng lẽ bỏ qua.
3. Mọi truy vấn phễu phải nối qua `sub_channel`; không được bịa ra `campaign_id` trong `fact_loan`.

### Trạng thái hồ sơ — suy ra, không có sẵn

Không có cột `status`. Trạng thái được suy ra và **phải** đóng băng trong semantic layer để mọi nơi hiểu giống nhau:

| Trạng thái | Điều kiện | Số lượng |
|---|---|---:|
| `REJECTED` | `application_id` có trong `fact_reject` | 1 062 |
| `DISBURSED` | `disbursement_date IS NOT NULL` | 1 625 |
| `SETTLED` | `settlement_date IS NOT NULL` (tập con của DISBURSED) | 156 |

Đã kiểm chứng: `REJECTED` và `DISBURSED` loại trừ nhau hoàn toàn, và `1 062 + 1 625 = 2 687`. Không có hồ sơ nào "đang treo".

**Bẫy số học:** 1 062 hồ sơ bị từ chối có `loan_amount`, `tenure`, `nominal_interest_rate`, `loan_balance` đều **NULL**. Nếu tính `AVG(loan_amount)` trên toàn bảng, Postgres tự bỏ NULL nên ra đúng. Nhưng nếu tính `SUM(loan_amount)/COUNT(*)` thì sai 39%. Semantic layer phải định nghĩa rõ mẫu số cho từng chỉ số.

## 2.2 Star schema đích

```
                        +------------------+
                        |   dim_campaign   |   (suy ra tu fact_lead)
                        |  PK sub_channel  |
                        +--------+---------+
                                 |
        +------------------------+------------------------+
        |                        |                        |
+-------v--------+      +--------v---------+              |
|   fact_lead    |      |    fact_loan     |              |
|  PK lead_id    |      | PK application_id|              |
|  FK sub_channel|      | FK sub_channel   |              |
|  FK customer_id|      | FK customer_id   |              |
|     (nullable) |      +--------+---------+              |
+----------------+               | 1:1 / 1:0..1           |
                    +------------+------------+-----------+
                    |            |            |
        +-----------v--+ +-------v------+ +--v-------------------+
        | fact_reject  | | fact_loan_pnl| |fact_digital_footprint|
        +--------------+ +--------------+ +----------------------+
                                 |
                        +--------v---------+
                        |  dim_customer    |
                        |  PK customer_id  |
                        +------------------+
```

Ngoài ra dựng thêm 3 **mart** (bảng vật lý, refresh sau ETL) để agent không phải join 5 bảng mỗi lần:

| Mart | Grain | Dùng cho |
|---|---|---|
| `mart_application` | 1 application | D1 dashboard, phân tích phễu, P&L |
| `mart_customer_value` | 1 khách hàng | D2 chân dung, D3 CLV |
| `mart_campaign_daily` | campaign × ngày | biểu đồ xu hướng |

## 2.3 DDL

### Schema `raw` — ảnh chụp nguyên trạng từ Excel

```sql
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE raw.dim_customer (
    customer_id        TEXT PRIMARY KEY,
    age                SMALLINT  NOT NULL,
    customer_open_date DATE      NOT NULL,
    occupation         TEXT      NOT NULL,
    active_status      TEXT      NOT NULL,
    has_app            BOOLEAN   NOT NULL,
    income             BIGINT    NOT NULL       -- VND/thang
);

CREATE TABLE raw.fact_lead (
    lead_id       TEXT PRIMARY KEY,
    customer_id   TEXT REFERENCES raw.dim_customer(customer_id),  -- NULL voi lead moi
    partner_code  TEXT      NOT NULL,
    channel       TEXT      NOT NULL,
    sub_channel   TEXT      NOT NULL,
    create_at     TIMESTAMP NOT NULL,
    product_id    TEXT      NOT NULL,
    campaign_id   TEXT      NOT NULL,
    campaign_name TEXT      NOT NULL,
    utm_source    TEXT      NOT NULL,
    utm_medium    TEXT      NOT NULL
);
CREATE INDEX ix_lead_campaign_date ON raw.fact_lead (campaign_id, create_at);
CREATE INDEX ix_lead_subchannel    ON raw.fact_lead (sub_channel);

CREATE TABLE raw.fact_loan (
    application_id        TEXT PRIMARY KEY,
    customer_id           TEXT NOT NULL REFERENCES raw.dim_customer(customer_id),
    product_id            TEXT NOT NULL,
    product_name          TEXT NOT NULL,
    create_at             TIMESTAMP NOT NULL,
    disbursement_date     TIMESTAMP,          -- NULL => chua/khong giai ngan
    settlement_date       TIMESTAMP,
    partner_code          TEXT NOT NULL,
    channel               TEXT NOT NULL,
    sub_channel           TEXT NOT NULL,
    tenure                SMALLINT,           -- thang; NULL khi bi tu choi
    no_paid               SMALLINT,
    last_duedate          TIMESTAMP,
    last_dayslate         SMALLINT,
    max_dayslate          SMALLINT,
    nominal_interest_rate NUMERIC(5,2),       -- %/thang, quan sat 1.50-2.60
    loan_amount           BIGINT,
    loan_number_rank      SMALLINT NOT NULL,  -- 1 = khoan vay dau tien
    loan_balance          BIGINT
);
CREATE INDEX ix_loan_customer   ON raw.fact_loan (customer_id);
CREATE INDEX ix_loan_subchannel ON raw.fact_loan (sub_channel);
CREATE INDEX ix_loan_create     ON raw.fact_loan (create_at);

CREATE TABLE raw.fact_reject (
    loan_application_id TEXT PRIMARY KEY REFERENCES raw.fact_loan(application_id),
    reason_level_1      TEXT NOT NULL,
    reason_level_2      TEXT NOT NULL
);

CREATE TABLE raw.loan_application_pnl (
    loan_application_id  TEXT PRIMARY KEY REFERENCES raw.fact_loan(application_id),
    interest_income      BIGINT        NOT NULL DEFAULT 0,
    overdue_interest     BIGINT        NOT NULL DEFAULT 0,
    early_paid_off_fee   BIGINT        NOT NULL DEFAULT 0,
    processing_fee       BIGINT        NOT NULL DEFAULT 0,
    loan_processing_cost NUMERIC(18,4) NOT NULL DEFAULT 0,
    funding_cost         BIGINT        NOT NULL DEFAULT 0,
    lead_cost            NUMERIC(18,4) NOT NULL DEFAULT 0,
    credit_loss          BIGINT        NOT NULL DEFAULT 0,
    operation_cost       NUMERIC(18,4) NOT NULL DEFAULT 0,
    marketing_cost       NUMERIC(18,4) NOT NULL DEFAULT 0,
    partner_fee          BIGINT        NOT NULL DEFAULT 0,
    collection_cost      NUMERIC(18,4) NOT NULL DEFAULT 0
);

CREATE TABLE raw.fact_digital_footprint (
    loan_application_id  TEXT PRIMARY KEY REFERENCES raw.fact_loan(application_id),
    device_os            TEXT    NOT NULL,
    device_price_segment TEXT    NOT NULL,
    form_filling_time    INTEGER NOT NULL,   -- giay; CO gia tri am, xem 2.5
    ip_address           INET,
    geo_location_match   BOOLEAN NOT NULL
);
```

> **Chuẩn hoá tên cột:** Excel dùng lẫn lộn `Customer_id`, `Age`, `Processing_Fee`, `Customer_open_date`. ETL hạ hết về `snake_case` ngay ở bước load. Không bao giờ để tên cột hoa/thường lẫn lộn chạm tới LLM — đó là nguồn sinh SQL sai một cách âm thầm.

### Schema `mart`

```sql
CREATE SCHEMA IF NOT EXISTS mart;

-- Dimension suy ra tu fact_lead
CREATE TABLE mart.dim_campaign AS
SELECT DISTINCT
    sub_channel,                 -- PK tu nhien
    campaign_id, campaign_name, channel, partner_code, product_id,
    utm_source, utm_medium
FROM raw.fact_lead;
ALTER TABLE mart.dim_campaign ADD PRIMARY KEY (sub_channel);
```

```sql
-- Bang det muc application: noi 5 nguon, gan trang thai, gan P&L
CREATE TABLE mart.mart_application AS
SELECT
    l.application_id,
    l.customer_id,
    c.campaign_id, c.campaign_name, c.channel, c.sub_channel, c.partner_code,
    l.product_id, l.product_name,
    l.create_at, l.disbursement_date, l.settlement_date,
    CASE WHEN r.loan_application_id IS NOT NULL THEN 'REJECTED'
         WHEN l.settlement_date   IS NOT NULL   THEN 'SETTLED'
         WHEN l.disbursement_date IS NOT NULL   THEN 'DISBURSED'
         ELSE 'UNKNOWN' END                      AS application_status,
    (r.loan_application_id IS NOT NULL)          AS is_rejected,
    (l.disbursement_date   IS NOT NULL)          AS is_disbursed,
    r.reason_level_1, r.reason_level_2,
    l.tenure, l.nominal_interest_rate, l.loan_amount, l.loan_balance,
    l.loan_number_rank, (l.loan_number_rank > 1) AS is_repeat_loan,
    l.no_paid, l.last_dayslate, l.max_dayslate,
    -- P&L
    p.interest_income, p.overdue_interest, p.early_paid_off_fee, p.processing_fee,
    p.loan_processing_cost, p.funding_cost, p.lead_cost, p.credit_loss,
    p.operation_cost, p.marketing_cost, p.partner_fee, p.collection_cost,
    (p.interest_income + p.overdue_interest + p.early_paid_off_fee + p.processing_fee)
        AS total_revenue,
    (p.loan_processing_cost + p.funding_cost + p.lead_cost + p.credit_loss
     + p.operation_cost + p.marketing_cost + p.partner_fee + p.collection_cost)
        AS total_cost,
    (p.interest_income + p.overdue_interest + p.early_paid_off_fee + p.processing_fee)
    - (p.loan_processing_cost + p.funding_cost + p.lead_cost + p.credit_loss
     + p.operation_cost + p.marketing_cost + p.partner_fee + p.collection_cost)
        AS net_profit,
    (p.marketing_cost + p.lead_cost)             AS acquisition_spend,
    -- Digital footprint
    d.device_os, d.device_price_segment, d.geo_location_match,
    NULLIF(GREATEST(d.form_filling_time, 0), 0)  AS form_filling_time_sec,  -- xem DQ-02
    -- Customer
    cu.age, cu.occupation, cu.income, cu.has_app, cu.customer_open_date,
    CASE WHEN cu.income <  8000000 THEN '<8M'
         WHEN cu.income < 12000000 THEN '8-12M'
         WHEN cu.income < 20000000 THEN '12-20M'
         ELSE '>=20M' END                        AS income_band,
    CASE WHEN cu.age <= 25 THEN '20-25' WHEN cu.age <= 30 THEN '26-30'
         WHEN cu.age <= 35 THEN '31-35' WHEN cu.age <= 45 THEN '36-45'
         ELSE '46-55' END                        AS age_band
FROM raw.fact_loan l
JOIN mart.dim_campaign          c  ON c.sub_channel         = l.sub_channel
JOIN raw.loan_application_pnl   p  ON p.loan_application_id = l.application_id
JOIN raw.fact_digital_footprint d  ON d.loan_application_id = l.application_id
JOIN raw.dim_customer          cu  ON cu.customer_id        = l.customer_id
LEFT JOIN raw.fact_reject       r  ON r.loan_application_id = l.application_id;

ALTER TABLE mart.mart_application ADD PRIMARY KEY (application_id);
CREATE INDEX ix_ma_campaign ON mart.mart_application (campaign_id);
CREATE INDEX ix_ma_customer ON mart.mart_application (customer_id);
CREATE INDEX ix_ma_status   ON mart.mart_application (application_status);
```

```sql
-- Muc khach hang: dung cho chan dung & CLV
CREATE TABLE mart.mart_customer_value AS
WITH agg AS (
  SELECT customer_id,
         COUNT(*)                             AS n_applications,
         COUNT(*) FILTER (WHERE is_disbursed) AS n_disbursed,
         COUNT(*) FILTER (WHERE is_rejected)  AS n_rejected,
         MAX(loan_number_rank)                AS max_loan_rank,
         SUM(loan_amount)                     AS total_loan_amount,
         SUM(net_profit)                      AS profit_to_date,
         SUM(acquisition_spend)               AS acquisition_spend,
         MAX(max_dayslate)                    AS worst_dayslate,
         MIN(create_at)                       AS first_application_at,
         MAX(create_at)                       AS last_application_at,
         MAX(disbursement_date)               AS last_disbursement_at
  FROM mart.mart_application GROUP BY customer_id
)
SELECT c.customer_id, c.age, c.occupation, c.income, c.has_app,
       c.active_status, c.customer_open_date,
       CASE WHEN c.income <  8000000 THEN '<8M'
            WHEN c.income < 12000000 THEN '8-12M'
            WHEN c.income < 20000000 THEN '12-20M'
            ELSE '>=20M' END                  AS income_band,
       CASE WHEN c.age <= 25 THEN '20-25' WHEN c.age <= 30 THEN '26-30'
            WHEN c.age <= 35 THEN '31-35' WHEN c.age <= 45 THEN '36-45'
            ELSE '46-55' END                  AS age_band,
       COALESCE(a.n_applications, 0)          AS n_applications,
       COALESCE(a.n_disbursed,    0)          AS n_disbursed,
       COALESCE(a.n_rejected,     0)          AS n_rejected,
       COALESCE(a.max_loan_rank,  0)          AS max_loan_rank,
       (COALESCE(a.max_loan_rank, 0) > 1)     AS is_repeat_customer,
       a.total_loan_amount,
       COALESCE(a.profit_to_date, 0)          AS profit_to_date,
       a.worst_dayslate,
       a.first_application_at, a.last_application_at, a.last_disbursement_at,
       (a.customer_id IS NULL)                AS is_never_applied
FROM raw.dim_customer c
LEFT JOIN agg a USING (customer_id);

ALTER TABLE mart.mart_customer_value ADD PRIMARY KEY (customer_id);
```

```sql
-- Xu huong theo ngay. Luu y: lead va application duoc dem doc lap roi noi theo ngay,
-- vi khong co khoa noi o muc ca the (xem 2.1).
CREATE TABLE mart.mart_campaign_daily AS
WITH lead_d AS (
  SELECT campaign_id, create_at::date AS d, COUNT(*) AS leads
  FROM raw.fact_lead GROUP BY 1,2),
app_d AS (
  SELECT campaign_id, create_at::date AS d,
         COUNT(*)                            AS applications,
         COUNT(*) FILTER (WHERE is_disbursed) AS disbursed,
         COUNT(*) FILTER (WHERE is_rejected)  AS rejected,
         SUM(loan_amount)                     AS loan_amount,
         SUM(total_revenue)                   AS revenue,
         SUM(total_cost)                      AS cost,
         SUM(net_profit)                      AS net_profit,
         SUM(acquisition_spend)               AS acquisition_spend
  FROM mart.mart_application GROUP BY 1,2)
SELECT COALESCE(l.campaign_id, a.campaign_id) AS campaign_id,
       COALESCE(l.d, a.d)                     AS activity_date,
       COALESCE(l.leads, 0)                   AS leads,
       COALESCE(a.applications, 0)            AS applications,
       COALESCE(a.disbursed, 0)               AS disbursed,
       COALESCE(a.rejected, 0)                AS rejected,
       a.loan_amount, a.revenue, a.cost, a.net_profit, a.acquisition_spend
FROM lead_d l
FULL OUTER JOIN app_d a ON l.campaign_id = a.campaign_id AND l.d = a.d;

ALTER TABLE mart.mart_campaign_daily ADD PRIMARY KEY (campaign_id, activity_date);
```

## 2.4 Giá trị tham chiếu — dùng làm golden set

Các con số dưới đây được tính độc lập bằng pandas, rồi **kiểm chứng lại lần hai** bằng cách dựng toàn bộ schema `raw` + `mart` trên DuckDB từ chính DDL trong tài liệu này và chạy lại các biểu thức SQL trong `config/semantic/metrics.yml`. Kết quả: **12/12 bất biến đạt, 6/6 chiến dịch × 8 chỉ số khớp tuyệt đối**. Agent **phải** tái tạo đúng chúng; chúng trở thành bộ đối chứng trong [13-testing-eval.md](13-testing-eval.md).

### Dashboard chiến dịch — kỳ dữ liệu 2026-08-01 đến 2026-08-31

| campaign_id | leads | apps | disb | lead to app | app to disb | Chi phí thu hút / khoản giải ngân | Doanh thu (VND) | Lợi nhuận ròng (VND) | ROMI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CMP-ZL-RL1 (Zalo Re-loan) | 1 414 | 486 | 447 | 34,4% | 92,0% | 141 590 | 759 988 373 | **+392 498 500** | **6,20** |
| CMP-GG-001 (Google) | 2 287 | 478 | 282 | 20,9% | 59,0% | 195 270 | 274 635 906 | +88 164 340 | 1,60 |
| CMP-FB-001 (Facebook) | 3 454 | 525 | 306 | 15,2% | 58,3% | 193 766 | 281 728 026 | +77 767 300 | 1,31 |
| CMP-TT-001 (TikTok) | 4 280 | 489 | 218 | 11,4% | 44,6% | 245 069 | 206 341 130 | +35 746 730 | 0,67 |
| CMP-PTN-MOMO (Momo) | 1 978 | 375 | 209 | 19,0% | 55,7% | 206 427 | 197 521 115 | **-17 529 770** | -0,41 |
| CMP-PTN-BRK01 (Broker) | 1 117 | 334 | 163 | 29,9% | 48,8% | 221 974 | 143 027 232 | **-66 794 870** | -1,85 |

Ba kết luận nghiệp vụ nổi lên ngay, và chúng là **đáp án** mà agent phải tự tìm ra:

1. **Zalo Remarketing áp đảo.** ROMI 6,20 so với 1,31-1,60 của các kênh thu hút khách mới. Lý do: đây là chiến dịch tái vay (`PRD-RL`), tỷ lệ duyệt 92% so với 45-59%, khoản vay lớn hơn hẳn (24,4 tỷ trên 447 khoản, tức khoảng 54,7 triệu mỗi khoản, so với khoảng 29 triệu ở nhóm khách mới). Bán cho khách cũ rẻ và lãi hơn nhiều lần so với đi tìm khách mới — đây chính là luận điểm CLV, và nó được chứng minh bằng chính dữ liệu chứ không phải bằng lý thuyết.
2. **Broker Network lỗ 66,8 triệu.** Tỷ lệ lead sang hồ sơ cao nhất trong nhóm khách mới (29,9%) nên nhìn qua tưởng tốt, nhưng duyệt chỉ 48,8% và `partner_fee` ăn mòn biên lợi nhuận. Phễu đẹp ở đầu, lỗ ở cuối — một chiến dịch mà chỉ số hư danh (vanity metric) đánh lừa người đọc.
3. **TikTok là cỗ máy sinh lead rác.** Nhiều lead nhất (4 280) và rẻ nhất, nhưng lead sang hồ sơ chỉ 11,4% và duyệt 44,6% — tệ nhất ở cả hai bước. Chi phí thu hút mỗi khoản giải ngân vì thế cao nhất (245k).

### Chân dung & CLV — 2 554 khách hàng có ít nhất một hồ sơ

| Chiều | Nhóm | n | Tỷ lệ vay lại | Lợi nhuận TB/khách (VND) |
|---|---|---:|---:|---:|
| Thu nhập | **>=20M** | **29** (mẫu quá nhỏ) | 86,2% | 451 054 |
| Thu nhập | **12-20M** | **797** | **20,7%** | **281 679** |
| Thu nhập | 8-12M | 1 071 | 10,6% | 173 352 |
| Thu nhập | <8M | 657 | 7,5% | 131 831 |
| Có app | **Có** | 1 442 | **16,6%** | **234 666** |
| Có app | Không | 1 112 | 10,3% | 154 195 |
| Tuổi | **46-55** | 513 | **21,6%** | 233 548 |
| Tuổi | 20-25 | 441 | 8,8% | 149 404 |
| Nghề | Freelancer | 375 | 12,8% | 220 200 |
| Nghề | Lai xe cong nghe | 346 | 14,2% | 180 937 |

Tỷ lệ vay lại toàn tập: **13,8%** (353/2 554). Khách vay lại sinh lời trung bình **1 111 894 VND**, gấp **20,9 lần** khách chỉ vay một lần (53 318 VND).

**Ba cái bẫy nằm ngay trong chính bảng này**, và cách agent phải xử lý:

* **Bẫy 1 — nhóm thu nhập >=20M chỉ có n=29.** Tỷ lệ vay lại 86,2% trông chói lọi nhưng khoảng tin cậy Wilson 95% rộng cỡ [69%, 95%], không đủ chắc để ra quyết định ngân sách. Agent **phải** gắn cảnh báo cỡ mẫu. Xem [08](08-anti-hallucination.md) §4.
* **Bẫy 2 — nghề nghiệp gần như không phân hoá.** Lợi nhuận TB dao động 180k-220k trên n khoảng 360 mỗi nhóm, trong khi độ lệch chuẩn lợi nhuận cá thể là 738k. Chênh lệch nằm gọn trong nhiễu. Không được phát biểu "Freelancer sinh lời nhất". Đây là test case số 1 của bộ chống hallucination.
* **Bẫy 3 — `has_app` là tương quan, không phải nhân quả.** Khách có app sinh lời hơn 52%, nhưng rất có thể khách tốt thì mới cài app, chứ không phải cài app làm họ tốt lên. Agent được phép đề xuất *"thử nghiệm A/B đẩy cài app"*, **không** được phát biểu *"cài app làm tăng lợi nhuận 80k"*.

* **Bẫy 4 — trung bình che giấu cơ cấu thật.** Lợi nhuận trung bình mỗi khách là **+199 629 VND**, nhưng **trung vị là −86 175 VND**. **53,8%** khách (1 374/2 554) sinh lời âm, và **top 10% khách đóng góp 81,9%** tổng lợi nhuận trong khi decile cuối làm mất 149 triệu. Báo cáo con số trung bình một mình là đúng về số học nhưng sai về bức tranh — và một LLM sẽ làm đúng điều đó nếu không bị buộc. Mọi chỉ số trung bình trong catalog vì thế mang trường `must_report_with: [median, negative_profit_share]`.

### Phân bố lợi nhuận theo decile

| Decile | n | Lợi nhuận (VND) | % tổng |
|---|---:|---:|---:|
| 1 (cao nhất) | 256 | +417 413 721 | **81,9%** |
| 2 | 256 | +186 700 761 | 36,6% |
| 3 | 256 | +118 361 805 | 23,2% |
| 4 | 256 | +67 659 849 | 13,3% |
| 5 | 255 | +8 360 837 | 1,6% |
| 6–9 | 1 020 | −139 578 457 | −27,4% |
| 10 (thấp nhất) | 255 | **−149 066 307** | **−29,2%** |

Hệ quả nghiệp vụ: bài toán không phải "nâng giá trị trung bình" mà là **"tìm và nhân bản nhóm decile 1, đồng thời giảm chi phí thu hút của nhóm decile 10"**. Đó là hai việc khác hẳn nhau, và chỉ nhìn số trung bình thì không thấy.

### Tín hiệu rủi ro và gian lận

| Chiều | Nhóm | n hồ sơ | Tỷ lệ từ chối | Lợi nhuận TB |
|---|---|---:|---:|---:|
| `geo_location_match` | **false** | 180 | **45,6%** | 91 630 |
| `geo_location_match` | true | 2 507 | 39,1% | 196 792 |
| `device_os` | Windows | 130 | 49,2% | 129 342 |
| `device_os` | Android | 1 652 | 39,1% | 194 444 |

Lý do từ chối (1 062 hồ sơ): Nợ xấu CIC 364 · Thu nhập không đủ 327 · Hồ sơ không hợp lệ 215 · Nghi ngờ gian lận 156.

## 2.5 Vấn đề chất lượng dữ liệu

ETL phải kiểm tra và ghi toàn bộ các mục dưới đây vào bảng `ops.dq_result`. Mức `BLOCK` làm ETL dừng; `WARN` cho chạy tiếp nhưng agent phải biết để chú thích.

| ID | Vấn đề | Số lượng | Mức | Xử lý |
|---|---|---:|---|---|
| DQ-01 | `disbursement_date` sớm hơn `create_at` | 6 | WARN | Giữ nguyên, gắn cờ `dq_flag_date_order`; loại khỏi chỉ số "thời gian duyệt" |
| DQ-02 | `form_filling_time` nhỏ hơn hoặc bằng 0 (thấp nhất -53 giây) | 9 | WARN | Chuyển thành NULL trong mart; ghi log |
| DQ-03 | Toàn bộ giao dịch chỉ nằm trong tháng 8/2026 | 31 ngày | WARN | **Chặn mọi phát biểu về xu hướng liên tháng hoặc YoY**. Metric so sánh kỳ phải trả lỗi `INSUFFICIENT_HISTORY` |
| DQ-04 | `fact_lead` không có khoá ngoại tới `fact_loan` | — | INFO | Phễu là tỷ lệ tổng hợp; bắt buộc chú thích (xem §2.1) |
| DQ-05 | `fact_lead.customer_id` NULL ở 13 116/14 530 dòng (chỉ chiến dịch Zalo re-loan có) | 90,3% | INFO | Không dùng cột này để tính chỉ số mức khách hàng trên toàn bộ lead |
| DQ-06 | 1 062 hồ sơ bị từ chối có `loan_amount`, `tenure`, `rate` đều NULL | 39,5% | INFO | Đúng về nghiệp vụ. Mọi chỉ số trung bình phải khai báo mẫu số rõ ràng |
| DQ-07 | 347 khách hàng trong `dim_customer` chưa có hồ sơ nào | 12,0% | INFO | Là tập "chưa kích hoạt" — chính là đối tượng của khuyến nghị D3 |
| DQ-08 | Tên cột Excel lẫn hoa/thường | 6 cột | BLOCK nếu lệch | ETL chuẩn hoá snake_case và **assert** danh sách cột khớp hợp đồng |
| DQ-09 | `loan_balance` khác `loan_amount` ở 1 219 hồ sơ | 45,4% | INFO | Đúng — khách đã trả bớt. Không được dùng lẫn hai cột |

### Kiểm tra bất biến (invariant) chạy sau mỗi lần ETL

| ID | Bất biến | Kỳ vọng |
|---|---|---|
| INV-1 | Tập `application_id` đồng nhất giữa `fact_loan`, `loan_application_pnl`, `fact_digital_footprint` | bằng nhau |
| INV-2 | `REJECTED` và `DISBURSED` loại trừ nhau | giao = rỗng |
| INV-3 | rejected + disbursed = tổng số hồ sơ | 1 062 + 1 625 = 2 687 |
| INV-4 | Mọi `customer_id` trong `fact_loan` tồn tại trong `dim_customer` | 100% |
| INV-5 | Mọi `sub_channel` trong `fact_loan` có trong `dim_campaign` | 100% |
| INV-6 | Hồ sơ bị từ chối có tổng doanh thu bằng 0 | 0 VND |
| INV-7 | `mart_application` có đúng số dòng bằng `raw.fact_loan` (join không nhân dòng) | 2 687 |

Bất kỳ INV nào fail thì ETL trả exit code khác 0 và agent từ chối phục vụ (readiness probe fail). Thà không trả lời còn hơn trả lời trên dữ liệu vỡ.

## 2.6 Luồng ETL

```
data/full_schema_mock_v2.xlsx  (hoac data/parquet/)
        |  etl/load_excel.py     pandas -> chuan hoa ten cot -> ep kieu -> COPY
        v
   schema raw.*                 anh chup nguyen trang, co rang buoc khoa
        |  etl/dq_checks.py      DQ-01..09 + INV-1..7 -> ops.dq_result
        |  etl/build_marts.py    dung dim_campaign + 3 mart
        v
   schema mart.*                agent CHI DOC o day
        |
   schema ops.*                 dq_result, etl_run, agent_trace
```

Chạy lại được nhiều lần (idempotent): mỗi lần chạy `TRUNCATE` rồi nạp lại trong một transaction. Quy mô 24 000 dòng nên toàn bộ ETL mất vài giây — không cần incremental load ở PoC.

Nguồn vào có thể là Excel hoặc thư mục `data/parquet/` (đã có sẵn, tên cột đã snake_case). `etl/load_excel.py` nhận cờ `--source {excel,parquet}`.
