"""Kiem tra tang truy cap du lieu (T04). Can Postgres cua profile test (T02
da nap du lieu) - `docker compose -f docker-compose.dev.yml up -d`.

`test_agent_role_cannot_write` la phep thu QUAN TRONG NHAT trong file nay:
no chung minh mot INSERT thuc su bi Postgres tu choi khi dung dung vai tro
chi-doc, khong phai chi tin vao cau hinh.

Dinh danh vai tro chi-doc noi day: profile `test` (config/profiles/test.yaml,
file protected) tro CA BA connection string ve mkt_owner de don gian, nen
`get_engine_ro()` trong profile test KHONG thuc su la mkt_agent_ro. Vi vay
test nay tu dung mot DSN rieng, tro dung vao vai tro mkt_agent_ro da duoc
etl/bootstrap_infra.py tao (mat khau TEST_ROLE_PASSWORDS, CHI dung cho
Postgres cuc bo trong docker-compose.dev.yml).
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.contracts import MetricRequest
from app.data.cache import AnswerCache, MetricResultCache, make_cache_key
from app.data.engines import assert_read_only_role, get_engine_ro, get_engine_trace
from app.data.repository import SqlMetricRunner
from app.errors import ReadOnlyViolation
from app.semantic.catalog import load_catalog
from etl.bootstrap_infra import TEST_ROLE_PASSWORDS

_AGENT_RO_TEST_DSN = (
    f"postgresql+psycopg://mkt_agent_ro:{TEST_ROLE_PASSWORDS['ro_pass']}"
    "@localhost:55432/mkt_insight"
)


def _skip_if_unreachable(engine: Engine) -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


@pytest.fixture(scope="module")
def agent_ro_engine() -> Engine:
    engine = create_engine(_AGENT_RO_TEST_DSN, pool_pre_ping=True)
    _skip_if_unreachable(engine)
    yield engine
    engine.dispose()


def test_agent_role_cannot_write(agent_ro_engine: Engine) -> None:
    """PHAI PASS: INSERT bang mkt_agent_ro bi Postgres tu choi."""
    assert_read_only_role(agent_ro_engine)  # khong raise = dat


def test_agent_role_can_still_read(agent_ro_engine: Engine) -> None:
    with agent_ro_engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM mart.mart_application")).scalar()
    assert n == 2687


def test_agent_role_cannot_touch_raw_schema(agent_ro_engine: Engine) -> None:
    """mkt_agent_ro chi duoc GRANT USAGE tren schema mart, khong phai raw
    (etl/sql/00_roles.sql: "REVOKE ALL ON SCHEMA raw FROM mkt_agent_ro")."""
    with pytest.raises(Exception, match="permission denied|does not exist"), agent_ro_engine.connect() as conn:
        conn.execute(text("SELECT COUNT(*) FROM raw.fact_loan"))


def test_assert_read_only_role_raises_when_role_can_actually_write() -> None:
    """Dat gia: neu mot engine THAT CO the ghi (vi du engine_admin), ham phai
    phat hien va raise ReadOnlyViolation - do la duong "phong ve that bai"
    (fail loudly) can kiem chung, khong chi duong thanh cong."""
    from app.data.engines import get_engine_admin

    _skip_if_unreachable(get_engine_admin())
    with pytest.raises(ReadOnlyViolation):
        assert_read_only_role(get_engine_admin())


def test_engine_ro_connects_in_test_profile() -> None:
    _skip_if_unreachable(get_engine_ro())
    with get_engine_ro().connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM mart.mart_customer_value")).scalar()
    assert n == 2901


# =============================================================================
# SqlMetricRunner - thuc thi CompiledQuery -> Fact co dia chi
# =============================================================================

def test_metric_runner_produces_addressable_fact() -> None:
    _skip_if_unreachable(get_engine_ro())
    runner = SqlMetricRunner(catalog=load_catalog())
    fact = runner.run(
        MetricRequest(metrics=("romi", "net_profit"), dimensions=("campaign_id",),
                      order_by="romi", order_desc=False, limit=10),
        fact_id="F1", title="ROMI theo chien dich",
    )
    assert fact.row_count == 6
    assert fact.rows[0]["_ref"] == "F1.r1"
    # Sap tang dan theo romi -> hang dau la campaign lo nang nhat
    assert fact.rows[0]["campaign_id"] == "CMP-PTN-BRK01"
    assert float(fact.rows[0]["romi"]) == pytest.approx(-1.846089, abs=1e-4)
    col_names = {c.name for c in fact.columns}
    assert {"campaign_id", "romi", "net_profit", "_n_rows"} <= col_names


# =============================================================================
# Cache
# =============================================================================

def test_metric_result_cache_roundtrip() -> None:
    from app.contracts import Fact

    cache = MetricResultCache(ttl_seconds=60)
    fact = Fact(fact_id="F1", title="t", query_id="q1", sql="SELECT 1",
                columns=[], rows=[], row_count=0)
    assert cache.get("q1") is None
    cache.set("q1", fact)
    assert cache.get("q1") is fact


def test_metric_result_cache_disabled_when_ttl_zero() -> None:
    from app.contracts import Fact

    cache = MetricResultCache(ttl_seconds=0)
    fact = Fact(fact_id="F1", title="t", query_id="q1", sql="SELECT 1",
                columns=[], rows=[], row_count=0)
    cache.set("q1", fact)
    assert cache.get("q1") is None


def test_answer_cache_roundtrip() -> None:
    _skip_if_unreachable(get_engine_trace())
    cache = AnswerCache()
    key = make_cache_key("cau hoi test", "pv1", "mv1", "run_1")

    cache.set(key, "**Tra loi mau**", {"facts": []}, trust_score=0.91, ttl_seconds=60)
    got = cache.get(key)
    assert got is not None
    assert got.answer_md == "**Tra loi mau**"
    assert got.trust_score == pytest.approx(0.91)


def test_answer_cache_ignores_ttl_zero_or_negative() -> None:
    """ttl_seconds <= 0 (profile test) -> khong ghi gi ca, khong co dong rac."""
    _skip_if_unreachable(get_engine_trace())
    cache = AnswerCache()
    key = make_cache_key("cau hoi khac", "pv1", "mv1", "run_1")
    cache.set(key, "khong nen luu", {}, trust_score=None, ttl_seconds=0)
    assert cache.get(key) is None


def test_answer_cache_expired_row_is_not_returned() -> None:
    """Ghi thang mot dong da het han (bo qua AnswerCache.set - de kiem tra
    dung dieu kien WHERE expires_at > now() trong get())."""
    _skip_if_unreachable(get_engine_trace())
    key = make_cache_key("cau hoi da het han", "pv1", "mv1", "run_1")
    with get_engine_trace().connect() as conn:
        conn.execute(
            text(
                "INSERT INTO ops.answer_cache (cache_key, answer_md, evidence, expires_at) "
                "VALUES (:k, 'cu', '{}'::jsonb, now() - interval '1 hour') "
                "ON CONFLICT (cache_key) DO UPDATE SET expires_at = EXCLUDED.expires_at"
            ),
            {"k": key},
        )
        conn.commit()
    assert AnswerCache().get(key) is None
