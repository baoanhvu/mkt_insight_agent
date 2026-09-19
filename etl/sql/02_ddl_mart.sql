-- =============================================================================
-- 02_ddl_mart.sql - Bang mart. Agent CHI doc o day.
-- =============================================================================
-- Chay bang mkt_owner, SAU khi 01_ddl_raw.sql da nap xong du lieu.
--
-- TOAN BO SQL trong file nay da duoc kiem chung tren du lieu that ngay 2026-09-19:
-- no tai tao dung 12/12 bat bien va dung 6/6 gia tri ROMI tham chieu trong
-- docs/02-data-model.md muc 2.4.
-- =============================================================================

DROP VIEW  IF EXISTS mart.v_customer_segment  CASCADE;
DROP TABLE IF EXISTS mart.mart_campaign_daily CASCADE;
DROP TABLE IF EXISTS mart.mart_customer_value CASCADE;
DROP TABLE IF EXISTS mart.mart_application    CASCADE;
DROP TABLE IF EXISTS mart.dim_campaign        CASCADE;

-- -----------------------------------------------------------------------------
-- dim_campaign - dimension SUY RA tu fact_lead.
-- Khoa tu nhien la sub_channel, vi day la cau noi DUY NHAT toi fact_loan.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.dim_campaign AS
SELECT DISTINCT
    sub_channel,
    campaign_id, campaign_name, channel, partner_code, product_id,
    utm_source, utm_medium
FROM raw.fact_lead;

ALTER TABLE mart.dim_campaign ADD PRIMARY KEY (sub_channel);
CREATE UNIQUE INDEX ux_dim_campaign_id ON mart.dim_campaign (campaign_id);

COMMENT ON TABLE mart.dim_campaign IS
  '6 chien dich. sub_channel la khoa 1-1 voi campaign_id trong bo du lieu nay.';

-- -----------------------------------------------------------------------------
-- mart_application - bang det muc ho so. Nguon chinh cho D1.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.mart_application AS
SELECT
    l.application_id,
    l.customer_id,
    c.campaign_id, c.campaign_name, c.channel, c.sub_channel, c.partner_code,
    l.product_id, l.product_name,
    l.create_at, l.disbursement_date, l.settlement_date,
    CASE WHEN r.loan_application_id IS NOT NULL THEN 'REJECTED'
         WHEN l.settlement_date     IS NOT NULL THEN 'SETTLED'
         WHEN l.disbursement_date   IS NOT NULL THEN 'DISBURSED'
         ELSE 'UNKNOWN' END                      AS application_status,
    (r.loan_application_id IS NOT NULL)          AS is_rejected,
    (l.disbursement_date   IS NOT NULL)          AS is_disbursed,
    r.reason_level_1, r.reason_level_2,
    l.tenure, l.nominal_interest_rate, l.loan_amount, l.loan_balance,
    l.loan_number_rank, (l.loan_number_rank > 1) AS is_repeat_loan,
    l.no_paid, l.last_dayslate, l.max_dayslate,

    -- P&L nguyen thuy
    p.interest_income, p.overdue_interest, p.early_paid_off_fee, p.processing_fee,
    p.loan_processing_cost, p.funding_cost, p.lead_cost, p.credit_loss,
    p.operation_cost, p.marketing_cost, p.partner_fee, p.collection_cost,

    -- P&L tong hop
    (p.interest_income + p.overdue_interest + p.early_paid_off_fee + p.processing_fee)
        AS total_revenue,
    (p.loan_processing_cost + p.funding_cost + p.lead_cost + p.credit_loss
     + p.operation_cost + p.marketing_cost + p.partner_fee + p.collection_cost)
        AS total_cost,
    (p.interest_income + p.overdue_interest + p.early_paid_off_fee + p.processing_fee)
    - (p.loan_processing_cost + p.funding_cost + p.lead_cost + p.credit_loss
     + p.operation_cost + p.marketing_cost + p.partner_fee + p.collection_cost)
        AS net_profit,
    -- KHONG gom partner_fee: xem docs/14-roadmap-risks.md cau hoi Q7
    (p.marketing_cost + p.lead_cost)             AS acquisition_spend,

    -- Dau vet so
    d.device_os, d.device_price_segment, d.geo_location_match,
    NULLIF(GREATEST(d.form_filling_time, 0), 0)  AS form_filling_time_sec,  -- DQ-02

    -- Khach hang
    cu.age, cu.occupation, cu.income, cu.has_app, cu.customer_open_date,
    CASE WHEN cu.income <  8000000 THEN '<8M'
         WHEN cu.income < 12000000 THEN '8-12M'
         WHEN cu.income < 20000000 THEN '12-20M'
         ELSE '>=20M' END                        AS income_band,
    CASE WHEN cu.age <= 25 THEN '20-25' WHEN cu.age <= 30 THEN '26-30'
         WHEN cu.age <= 35 THEN '31-35' WHEN cu.age <= 45 THEN '36-45'
         ELSE '46-55' END                        AS age_band,

    -- Co chat luong du lieu
    (l.disbursement_date < l.create_at)          AS dq_flag_date_order           -- DQ-01
FROM raw.fact_loan l
JOIN mart.dim_campaign          c  ON c.sub_channel         = l.sub_channel
JOIN raw.loan_application_pnl   p  ON p.loan_application_id = l.application_id
JOIN raw.fact_digital_footprint d  ON d.loan_application_id = l.application_id
JOIN raw.dim_customer          cu  ON cu.customer_id        = l.customer_id
LEFT JOIN raw.fact_reject       r  ON r.loan_application_id = l.application_id;

ALTER TABLE mart.mart_application ADD PRIMARY KEY (application_id);
CREATE INDEX ix_ma_campaign    ON mart.mart_application (campaign_id);
CREATE INDEX ix_ma_customer    ON mart.mart_application (customer_id);
CREATE INDEX ix_ma_status      ON mart.mart_application (application_status);
CREATE INDEX ix_ma_create_date ON mart.mart_application ((create_at::date));
CREATE INDEX ix_ma_income_band ON mart.mart_application (income_band);

COMMENT ON TABLE mart.mart_application IS
  '2 687 dong, dung bang so dong cua raw.fact_loan (bat bien INV-7: join khong nhan dong).';

-- -----------------------------------------------------------------------------
-- mart_customer_value - muc khach hang. Nguon chinh cho D2 va D3.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.mart_customer_value AS
WITH agg AS (
  SELECT customer_id,
         COUNT(*)                             AS n_applications,
         COUNT(*) FILTER (WHERE is_disbursed)  AS n_disbursed,
         COUNT(*) FILTER (WHERE is_rejected)   AS n_rejected,
         MAX(loan_number_rank)                 AS max_loan_rank,
         SUM(loan_amount)                      AS total_loan_amount,
         SUM(net_profit)                       AS profit_to_date,
         SUM(acquisition_spend)                AS acquisition_spend,
         MAX(max_dayslate)                     AS worst_dayslate,
         MIN(create_at)                        AS first_application_at,
         MAX(create_at)                        AS last_application_at,
         MAX(disbursement_date)                AS last_disbursement_at
  FROM mart.mart_application
  GROUP BY customer_id
)
SELECT c.customer_id, c.age, c.occupation, c.income, c.has_app,
       c.active_status, c.customer_open_date,
       CASE WHEN c.income <  8000000 THEN '<8M'
            WHEN c.income < 12000000 THEN '8-12M'
            WHEN c.income < 20000000 THEN '12-20M'
            ELSE '>=20M' END                   AS income_band,
       CASE WHEN c.age <= 25 THEN '20-25' WHEN c.age <= 30 THEN '26-30'
            WHEN c.age <= 35 THEN '31-35' WHEN c.age <= 45 THEN '36-45'
            ELSE '46-55' END                   AS age_band,
       COALESCE(a.n_applications, 0)           AS n_applications,
       COALESCE(a.n_disbursed,    0)           AS n_disbursed,
       COALESCE(a.n_rejected,     0)           AS n_rejected,
       COALESCE(a.max_loan_rank,  0)           AS max_loan_rank,
       (COALESCE(a.max_loan_rank, 0) > 1)      AS is_repeat_customer,
       a.total_loan_amount,
       COALESCE(a.profit_to_date, 0)           AS profit_to_date,
       a.acquisition_spend,
       a.worst_dayslate,
       a.first_application_at, a.last_application_at, a.last_disbursement_at,
       (a.customer_id IS NULL)                 AS is_never_applied
FROM raw.dim_customer c
LEFT JOIN agg a USING (customer_id);

ALTER TABLE mart.mart_customer_value ADD PRIMARY KEY (customer_id);
CREATE INDEX ix_mcv_repeat  ON mart.mart_customer_value (is_repeat_customer);
CREATE INDEX ix_mcv_income  ON mart.mart_customer_value (income_band);
CREATE INDEX ix_mcv_applied ON mart.mart_customer_value (is_never_applied);

COMMENT ON TABLE mart.mart_customer_value IS
  '2 901 khach, GOM ca 347 khach chua co ho so nao. Mau so mac dinh KHONG phai 2 554.';

-- -----------------------------------------------------------------------------
-- v_customer_segment - phan khuc bang LUAT tuong minh.
-- Luat chay THEO THU TU; moi khach roi vao phan khuc DAU TIEN khop.
-- Bat bien: KHONG co dong nao mang segment = '_unclassified'.
-- Dinh nghia goc: config/analytics.yaml -> segmentation.rules
-- -----------------------------------------------------------------------------
CREATE VIEW mart.v_customer_segment AS
WITH p75 AS (
    SELECT PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY profit_to_date) AS v
    FROM mart.mart_customer_value
    WHERE n_applications > 0
)
SELECT m.*,
       CASE
         WHEN COALESCE(m.worst_dayslate, 0) > 30 OR m.n_rejected >= 2
              THEN 'high_risk'
         WHEN m.is_repeat_customer AND m.profit_to_date >= (SELECT v FROM p75)
              THEN 'champion'
         WHEN m.is_repeat_customer
              THEN 'repeat_standard'
         WHEN m.n_disbursed >= 1 AND m.income_band IN ('12-20M', '>=20M')
              AND m.has_app AND COALESCE(m.worst_dayslate, 0) = 0
              THEN 'high_potential'
         WHEN m.n_disbursed >= 1 AND NOT m.has_app
              AND m.income_band IN ('12-20M', '>=20M')
              THEN 'app_gap'
         WHEN m.n_disbursed >= 1
              THEN 'dormant'
         WHEN m.n_applications >= 1
              THEN 'rejected_only'
         ELSE 'never_activated'
       END AS segment
FROM mart.mart_customer_value m;

COMMENT ON VIEW mart.v_customer_segment IS
  'Phan bo da kiem chung: rejected_only 1023, dormant 802, never_activated 347, '
  'champion 282, app_gap 159, high_potential 145, high_risk 97, repeat_standard 46. '
  'Tong 2 901, khong co _unclassified.';

-- -----------------------------------------------------------------------------
-- mart_campaign_daily - xu huong theo ngay.
-- Lead va ho so duoc dem DOC LAP roi noi theo (campaign_id, ngay), vi khong co
-- khoa noi o muc ca the. Moi ty le tu bang nay la TY LE TONG HOP.
-- -----------------------------------------------------------------------------
CREATE TABLE mart.mart_campaign_daily AS
WITH lead_d AS (
    SELECT campaign_id, create_at::date AS d, COUNT(*) AS leads
    FROM raw.fact_lead GROUP BY 1, 2
),
app_d AS (
    SELECT campaign_id, create_at::date AS d,
           COUNT(*)                             AS applications,
           COUNT(*) FILTER (WHERE is_disbursed)  AS disbursed,
           COUNT(*) FILTER (WHERE is_rejected)   AS rejected,
           SUM(loan_amount)                      AS loan_amount,
           SUM(total_revenue)                    AS revenue,
           SUM(total_cost)                       AS cost,
           SUM(net_profit)                       AS net_profit,
           SUM(acquisition_spend)                AS acquisition_spend
    FROM mart.mart_application GROUP BY 1, 2
)
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
CREATE INDEX ix_mcd_date ON mart.mart_campaign_daily (activity_date);

COMMENT ON TABLE mart.mart_campaign_daily IS
  '186 dong = 6 chien dich x 31 ngay. Ty le tinh tu bang nay la ty le TONG HOP '
  'muc chien dich, khong phai attribution tung lead (DQ-04).';

-- -----------------------------------------------------------------------------
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO mkt_agent_ro;
GRANT SELECT ON mart.v_customer_segment    TO mkt_agent_ro;
ANALYZE mart.mart_application;
ANALYZE mart.mart_customer_value;
ANALYZE mart.mart_campaign_daily;
