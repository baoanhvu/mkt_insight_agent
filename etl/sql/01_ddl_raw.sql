-- =============================================================================
-- 01_ddl_raw.sql - Anh chup nguyen trang tu Excel
-- =============================================================================
-- Chay bang mkt_owner.
-- Ten cot da duoc ETL ha ve snake_case. Excel dung lan lon Customer_id, Age,
-- Processing_Fee, Customer_open_date - khong bao gio de cach viet do cham toi LLM.
--
-- So dong ky vong (bat bien INV, kiem tra trong etl/dq_checks.py):
--   dim_customer 2 901 | fact_lead 14 530 | fact_loan 2 687
--   fact_reject 1 062  | loan_application_pnl 2 687 | fact_digital_footprint 2 687
-- =============================================================================

DROP TABLE IF EXISTS raw.fact_digital_footprint CASCADE;
DROP TABLE IF EXISTS raw.loan_application_pnl   CASCADE;
DROP TABLE IF EXISTS raw.fact_reject            CASCADE;
DROP TABLE IF EXISTS raw.fact_loan              CASCADE;
DROP TABLE IF EXISTS raw.fact_lead              CASCADE;
DROP TABLE IF EXISTS raw.dim_customer           CASCADE;

-- -----------------------------------------------------------------------------
CREATE TABLE raw.dim_customer (
    customer_id        TEXT     PRIMARY KEY,
    age                SMALLINT NOT NULL CHECK (age BETWEEN 18 AND 80),
    customer_open_date DATE     NOT NULL,
    occupation         TEXT     NOT NULL,
    active_status      TEXT     NOT NULL,
    has_app            BOOLEAN  NOT NULL,
    income             BIGINT   NOT NULL CHECK (income > 0)   -- VND/thang
);
COMMENT ON TABLE  raw.dim_customer IS '2 901 khach hang. 347 trong so do chua co ho so nao (DQ-07).';
COMMENT ON COLUMN raw.dim_customer.income IS 'Thu nhap thang, VND. Quan sat: 4,5tr - 40,2tr.';

-- -----------------------------------------------------------------------------
CREATE TABLE raw.fact_lead (
    lead_id       TEXT      PRIMARY KEY,
    customer_id   TEXT      REFERENCES raw.dim_customer(customer_id),
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
CREATE INDEX ix_lead_create_date   ON raw.fact_lead ((create_at::date));

COMMENT ON TABLE raw.fact_lead IS
  '14 530 lead. KHONG co khoa ngoai toi fact_loan - xem docs/02 muc 2.1. '
  'Cau noi duy nhat toi ho so vay la sub_channel.';
COMMENT ON COLUMN raw.fact_lead.customer_id IS
  'NULL o 13 116/14 530 dong (DQ-05). Chi chien dich tai vay CMP-ZL-RL1 co gia tri.';

-- -----------------------------------------------------------------------------
CREATE TABLE raw.fact_loan (
    application_id        TEXT      PRIMARY KEY,
    customer_id           TEXT      NOT NULL REFERENCES raw.dim_customer(customer_id),
    product_id            TEXT      NOT NULL,
    product_name          TEXT      NOT NULL,
    create_at             TIMESTAMP NOT NULL,
    disbursement_date     TIMESTAMP,          -- NULL => bi tu choi
    settlement_date       TIMESTAMP,
    partner_code          TEXT      NOT NULL,
    channel               TEXT      NOT NULL,
    sub_channel           TEXT      NOT NULL,
    tenure                SMALLINT,           -- thang; NULL khi bi tu choi
    no_paid               SMALLINT,
    last_duedate          TIMESTAMP,
    last_dayslate         SMALLINT,
    max_dayslate          SMALLINT,
    nominal_interest_rate NUMERIC(5,2),       -- %/thang; quan sat 1,50 - 2,60
    loan_amount           BIGINT,
    loan_number_rank      SMALLINT  NOT NULL CHECK (loan_number_rank >= 1),
    loan_balance          BIGINT
);
CREATE INDEX ix_loan_customer    ON raw.fact_loan (customer_id);
CREATE INDEX ix_loan_subchannel  ON raw.fact_loan (sub_channel);
CREATE INDEX ix_loan_create      ON raw.fact_loan (create_at);
CREATE INDEX ix_loan_create_date ON raw.fact_loan ((create_at::date));

COMMENT ON TABLE raw.fact_loan IS
  '2 687 ho so. KHONG co lead_id, KHONG co campaign_id. 1 062 ho so bi tu choi co '
  'loan_amount/tenure/rate/balance deu NULL (DQ-06) - dung la dung, khong phai loi.';
COMMENT ON COLUMN raw.fact_loan.loan_number_rank IS
  '1 = khoan vay dau tien. >1 tuong duong product_id = PRD-RL trong bo du lieu nay.';
COMMENT ON COLUMN raw.fact_loan.loan_balance IS
  'Khac loan_amount o 1 219/2 687 ho so (DQ-09) - khach da tra bot. Khong dung lan hai cot.';

-- -----------------------------------------------------------------------------
CREATE TABLE raw.fact_reject (
    loan_application_id TEXT PRIMARY KEY REFERENCES raw.fact_loan(application_id),
    reason_level_1      TEXT NOT NULL,
    reason_level_2      TEXT NOT NULL
);
COMMENT ON TABLE raw.fact_reject IS '1 062 ho so bi tu choi. Tap con cua fact_loan.';

-- -----------------------------------------------------------------------------
CREATE TABLE raw.loan_application_pnl (
    loan_application_id  TEXT          PRIMARY KEY REFERENCES raw.fact_loan(application_id),
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
COMMENT ON TABLE raw.loan_application_pnl IS
  '1:1 voi fact_loan. Ho so bi tu choi VAN co lead_cost, marketing_cost, '
  'operation_cost va loan_processing_cost - nen chung dong gop AM vao loi nhuan.';
COMMENT ON COLUMN raw.loan_application_pnl.partner_fee IS
  'Chi khac 0 o CMP-PTN-BRK01 (92 650 696) va CMP-PTN-MOMO (76 323 400).';

-- -----------------------------------------------------------------------------
CREATE TABLE raw.fact_digital_footprint (
    loan_application_id  TEXT    PRIMARY KEY REFERENCES raw.fact_loan(application_id),
    device_os            TEXT    NOT NULL,
    device_price_segment TEXT    NOT NULL,
    form_filling_time    INTEGER NOT NULL,   -- giay; CO gia tri am, xem DQ-02
    ip_address           INET,
    geo_location_match   BOOLEAN NOT NULL
);
COMMENT ON COLUMN raw.fact_digital_footprint.form_filling_time IS
  '9 gia tri khong duong (thap nhat -53). Mart chuyen chung thanh NULL (DQ-02).';
COMMENT ON COLUMN raw.fact_digital_footprint.geo_location_match IS
  'false o 180/2 687 ho so. Nhom nay co ty le tu choi 45,6% so voi 39,1%.';
