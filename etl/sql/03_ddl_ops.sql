-- =============================================================================
-- 03_ddl_ops.sql - Bang van hanh: ETL, chat luong du lieu, telemetry, prompt
-- =============================================================================
-- Chay bang mkt_owner.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS ops;

-- -----------------------------------------------------------------------------
-- ETL
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.etl_run (
    run_id        BIGSERIAL   PRIMARY KEY,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    source        TEXT        NOT NULL,          -- excel | parquet
    status        TEXT        NOT NULL,          -- RUNNING | OK | FAILED
    rows_loaded   JSONB,                         -- {"fact_lead": 14530, ...}
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS ops.dq_result (
    run_id     BIGINT      NOT NULL REFERENCES ops.etl_run(run_id) ON DELETE CASCADE,
    check_id   TEXT        NOT NULL,             -- DQ-01 | INV-3 ...
    severity   TEXT        NOT NULL,             -- INFO | WARN | BLOCK
    passed     BOOLEAN     NOT NULL,
    observed   JSONB,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, check_id)
);

-- /readyz doc view nay. Co dong nao -> tra 503 va agent tu choi phuc vu.
CREATE OR REPLACE VIEW ops.v_blocking_dq AS
SELECT d.*
FROM ops.dq_result d
JOIN (SELECT MAX(run_id) AS run_id FROM ops.etl_run WHERE status = 'OK') last
  ON last.run_id = d.run_id
WHERE d.severity = 'BLOCK' AND NOT d.passed;

-- -----------------------------------------------------------------------------
-- Telemetry  - mot dong moi luot tra loi
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.agent_trace (
    trace_id        UUID        PRIMARY KEY,
    session_id      TEXT,
    user_hash       TEXT,                        -- bam, khong luu id goc
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    question        TEXT        NOT NULL,
    question_norm   TEXT,
    intent          TEXT,
    playbook        TEXT,
    route_confidence NUMERIC(4,3),

    evidence        JSONB,                       -- truy van da chay + fingerprint ket qua
    answer_md       TEXT,
    checks          JSONB,                       -- ket qua tung lop L0..L5
    trust_score     NUMERIC(4,3),
    decision        TEXT,                        -- ANSWERED|HEDGED|ABSTAINED|BLOCKED|CANCELLED
    block_reason    TEXT,

    -- BA COT BAT BUOC. Thieu chung thi khi chat luong tut khong ai truy duoc
    -- la do sua prompt, doi model, hay du lieu thay doi.
    prompt_version  TEXT        NOT NULL,
    model_name      TEXT        NOT NULL,
    profile         TEXT        NOT NULL,        -- local | greennode | test
    metrics_version TEXT,
    data_version    TEXT,                        -- etl_run_id

    latency_ms      INTEGER,
    llm_calls       SMALLINT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,

    user_feedback   SMALLINT,                    -- -1 | 0 | 1  -> nguon cho golden set
    feedback_note   TEXT
);
CREATE INDEX IF NOT EXISTS ix_trace_created  ON ops.agent_trace (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_trace_decision ON ops.agent_trace (decision);
CREATE INDEX IF NOT EXISTS ix_trace_feedback ON ops.agent_trace (user_feedback)
    WHERE user_feedback IS NOT NULL;

-- Bang theo doi chat luong theo ngay. GET /api/admin/quality doc view nay.
CREATE OR REPLACE VIEW ops.v_quality_daily AS
SELECT created_at::date                                          AS day,
       COUNT(*)                                                  AS answers,
       AVG((checks->'numeric_grounding'->>'score')::numeric)      AS numeric_grounding_rate,
       AVG((checks->'entity_grounding'->>'score')::numeric)       AS entity_grounding_rate,
       AVG(trust_score)                                           AS avg_trust_score,
       AVG(CASE WHEN decision = 'BLOCKED'   THEN 1.0 ELSE 0 END)  AS block_rate,
       AVG(CASE WHEN decision = 'ABSTAINED' THEN 1.0 ELSE 0 END)  AS abstain_rate,
       AVG(CASE WHEN decision = 'HEDGED'    THEN 1.0 ELSE 0 END)  AS hedge_rate,
       AVG((checks->'judge'->>'contradiction_rate')::numeric)     AS judge_contradiction_rate,
       AVG(llm_calls)                                             AS llm_calls_per_answer,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)   AS p95_latency_ms
FROM ops.agent_trace
GROUP BY 1 ORDER BY 1 DESC;

-- -----------------------------------------------------------------------------
-- Cache cau tra loi  - dung chung giua cac replica
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.answer_cache (
    cache_key    TEXT        PRIMARY KEY,   -- hash(question_norm + prompt_ver + metrics_ver + data_ver)
    answer_md    TEXT        NOT NULL,
    evidence     JSONB       NOT NULL,
    trust_score  NUMERIC(4,3),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    hit_count    INTEGER     NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_cache_expires ON ops.answer_cache (expires_at);

-- -----------------------------------------------------------------------------
-- Prompt override  - sua qua trang admin khi chay nhieu replica
-- File trong image la baseline; override trong DB thang.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.prompt_override (
    prompt_id  TEXT        PRIMARY KEY,
    version    TEXT        NOT NULL,
    content    TEXT        NOT NULL,             -- YAML day du
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS ops.prompt_history (
    id         BIGSERIAL   PRIMARY KEY,
    prompt_id  TEXT        NOT NULL,
    version    TEXT        NOT NULL,
    content    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT
);
CREATE INDEX IF NOT EXISTS ix_prompt_hist ON ops.prompt_history (prompt_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- Buffer su kien SSE  - de client noi lai sau khi mat mang (Last-Event-ID)
-- Don dep bang cron hoac bang mot lan xoa luc khoi dong.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ops.stream_buffer (
    trace_id   UUID        NOT NULL,
    seq        INTEGER     NOT NULL,
    event      TEXT        NOT NULL,
    data       JSONB       NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trace_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_stream_created ON ops.stream_buffer (created_at);

-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA ops TO mkt_trace_rw;
GRANT INSERT, SELECT, UPDATE ON ALL TABLES IN SCHEMA ops TO mkt_trace_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ops TO mkt_trace_rw;
