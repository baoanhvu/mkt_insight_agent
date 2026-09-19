-- =============================================================================
-- 00_roles.sql - Tao schema va ba vai tro
-- =============================================================================
-- Chay MOT LAN, bang tai khoan quan tri cua vDB RDS, TRUOC khi chay ETL.
--   psql "$ADMIN_URL" -f etl/sql/00_roles.sql -v ro_pass=... -v owner_pass=... -v trace_pass=...
--
-- Day la hang rao THAT, khong phai quy uoc trong code. `default_transaction_read_only`
-- dat o muc role nghia la: ke ca khi moi lop kiem tra SQL trong code bi bo qua vi mot
-- loi lap trinh, mot cau DELETE van bi chinh PostgreSQL tu choi.
-- Xem docs/03-database-choice.md muc 3.3.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS ops;

-- -----------------------------------------------------------------------------
-- 1. Chu so huu: chay ETL, tao bang. CHI dung trong script ETL.
--    Khong bao gio nam trong process web.
-- -----------------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mkt_owner') THEN
    CREATE ROLE mkt_owner LOGIN PASSWORD :'owner_pass';
  END IF;
END $$;

GRANT ALL ON SCHEMA raw, mart, ops TO mkt_owner;
ALTER SCHEMA raw  OWNER TO mkt_owner;
ALTER SCHEMA mart OWNER TO mkt_owner;
ALTER SCHEMA ops  OWNER TO mkt_owner;

-- -----------------------------------------------------------------------------
-- 2. Vai tro AGENT: chay MOI truy van phuc vu cau tra loi.
--    CHI DOC, va chi o schema mart.
-- -----------------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mkt_agent_ro') THEN
    CREATE ROLE mkt_agent_ro LOGIN PASSWORD :'ro_pass';
  END IF;
END $$;

REVOKE ALL ON SCHEMA public FROM mkt_agent_ro;
REVOKE ALL ON SCHEMA raw    FROM mkt_agent_ro;   -- agent KHONG duoc cham schema raw
REVOKE ALL ON SCHEMA ops    FROM mkt_agent_ro;

GRANT USAGE ON SCHEMA mart TO mkt_agent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO mkt_agent_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO mkt_agent_ro;

-- Chan truy van chay loan va chan ghi o MUC DATABASE
ALTER ROLE mkt_agent_ro SET statement_timeout                    = '15s';
ALTER ROLE mkt_agent_ro SET idle_in_transaction_session_timeout   = '30s';
ALTER ROLE mkt_agent_ro SET default_transaction_read_only         = on;
ALTER ROLE mkt_agent_ro SET search_path                           = 'mart';
ALTER ROLE mkt_agent_ro SET work_mem                              = '32MB';
ALTER ROLE mkt_agent_ro SET lock_timeout                          = '5s';

-- -----------------------------------------------------------------------------
-- 3. Vai tro ghi telemetry: chi INSERT/SELECT vao schema ops.
-- -----------------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mkt_trace_rw') THEN
    CREATE ROLE mkt_trace_rw LOGIN PASSWORD :'trace_pass';
  END IF;
END $$;

REVOKE ALL ON SCHEMA raw, mart FROM mkt_trace_rw;
GRANT USAGE ON SCHEMA ops TO mkt_trace_rw;
GRANT INSERT, SELECT, UPDATE ON ALL TABLES IN SCHEMA ops TO mkt_trace_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ops TO mkt_trace_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops
  GRANT INSERT, SELECT, UPDATE ON TABLES TO mkt_trace_rw;
ALTER ROLE mkt_trace_rw SET statement_timeout = '10s';

-- -----------------------------------------------------------------------------
-- 4. Kiem tra: cau nay PHAI THAT BAI khi chay bang mkt_agent_ro.
--    app/settings.py chay dung phep thu nay luc khoi dong (assert_read_only_role)
--    va TU CHOI khoi dong neu no thanh cong.
-- -----------------------------------------------------------------------------
-- SET ROLE mkt_agent_ro;
-- CREATE TABLE mart.should_fail (x int);   -->  ERROR: permission denied
-- RESET ROLE;
