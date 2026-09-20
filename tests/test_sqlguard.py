"""Kiem tra app/data/sqlguard.py::SqlGuard - L0/L1, duong freeform (T12).
Xem docs/05-semantic-layer.md muc 5.6 (7 cua) va docs/17 T12.

THUAN - khong can Postgres: `SqlGuard` nhan mot schema TINH (khong truy van
DB) nen toan bo file nay chay duoc ngay, giong tinh than cua T09 (nguoi B).
"""

from __future__ import annotations

import pytest

from app.data.sqlguard import SqlGuard, build_sql_guard_from_config
from app.errors import (
    SQLForbiddenStatement,
    SQLParseError,
    SQLSchemaNotAllowed,
    SQLUnboundIdentifier,
)

_SCHEMA = {
    "mart": {
        "mart_application": {
            "campaign_id": "text", "campaign_name": "text", "channel": "text",
            "application_status": "text", "romi": "double precision",
            "net_profit": "double precision", "acquisition_spend": "double precision",
            "disbursed_loans": "bigint", "approval_rate": "double precision",
            "occupation": "text", "income_band": "text", "age_band": "text",
        },
        "mart_customer_value": {
            "customer_id": "text", "income_band": "text", "age_band": "text",
            "profit_to_date": "double precision", "n_disbursed": "bigint",
            "is_repeat_customer": "boolean",
        },
        "mart_campaign_daily": {
            "campaign_id": "text", "activity_date": "date", "leads": "bigint",
            "applications": "bigint", "disbursed": "bigint", "net_profit": "double precision",
        },
        "dim_campaign": {
            "campaign_id": "text", "campaign_name": "text", "channel": "text",
            "sub_channel": "text", "partner_code": "text",
        },
        "v_customer_segment": {
            "customer_id": "text", "segment": "text",
        },
    },
}

_ALLOWED_TABLES = frozenset({
    "mart.mart_application", "mart.mart_customer_value", "mart.mart_campaign_daily",
    "mart.dim_campaign", "mart.v_customer_segment",
})


@pytest.fixture
def guard() -> SqlGuard:
    return SqlGuard(_SCHEMA, _ALLOWED_TABLES, default_limit=500, max_limit=1000)


# -----------------------------------------------------------------------------
# Cua 1-2: dung mot cau lenh, phai la SELECT
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("statement", [
    "DROP TABLE x", "CREATE TABLE x (id int)", "INSERT INTO mart.mart_application VALUES (1)",
    "UPDATE mart.mart_application SET romi = 0", "DELETE FROM mart.mart_application",
    "ALTER TABLE mart.mart_application ADD COLUMN x int", "TRUNCATE mart.mart_application",
    "GRANT SELECT ON mart.mart_application TO public", "MERGE INTO mart.mart_application USING x ON true WHEN MATCHED THEN DELETE",
    "CALL some_proc()", "VACUUM mart.mart_application", "SET search_path = mart",
])
def test_forbidden_statement_types_are_blocked(guard: SqlGuard, statement: str) -> None:
    with pytest.raises(SQLForbiddenStatement):
        guard.validate(statement)


def test_drop_table_is_blocked(guard: SqlGuard) -> None:
    """Vi du dung dung ten trong docs/17 T12."""
    with pytest.raises(SQLForbiddenStatement):
        guard.validate("DROP TABLE x")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM mart.mart_application /* hidden */ ; DROP TABLE y",
    "SELECT * FROM mart.mart_application; SELECT * FROM mart.mart_application",
    "SELECT 1; SELECT 2; SELECT 3",
])
def test_multiple_statements_are_blocked_even_when_first_is_a_valid_select(
    guard: SqlGuard, sql: str,
) -> None:
    """Cau lenh AN sau dau ';' (kieu tan cong injection) phai bi chan boi
    quy tac 'dung MOT cau lenh', du cau dau la SELECT hop le."""
    with pytest.raises(SQLForbiddenStatement):
        guard.validate(sql)


def test_comment_does_not_defeat_the_statement_count_check(guard: SqlGuard) -> None:
    """So khop CHUOI se bi comment danh lua; kiem tra tren AST thi khong."""
    with pytest.raises(SQLForbiddenStatement):
        guard.validate("SELECT * FROM mart.mart_application /* ; harmless */; DROP TABLE y")


# -----------------------------------------------------------------------------
# Cua 3: cot phai phan giai duoc that (khong bia)
# -----------------------------------------------------------------------------

def test_unknown_column_is_blocked_with_correct_error_type(guard: SqlGuard) -> None:
    """Vi du dung dung trong docs/17 T12."""
    with pytest.raises(SQLUnboundIdentifier):
        guard.validate("SELECT fake_col FROM mart.mart_application")


@pytest.mark.parametrize("sql", [
    "SELECT romi_that_khong_ton_tai FROM mart.mart_application",
    "SELECT campaign_id, doanh_thu_bia FROM mart.mart_application",
    "SELECT a.campaign_id FROM mart.mart_application a WHERE a.cot_bia = 1",
    "SELECT segment_khong_co FROM mart.v_customer_segment",
    "SELECT romi FROM mart.mart_application ORDER BY cot_khong_ton_tai",
])
def test_various_unbound_columns_are_blocked(guard: SqlGuard, sql: str) -> None:
    with pytest.raises(SQLUnboundIdentifier):
        guard.validate(sql)


def test_column_from_a_different_allowed_table_is_still_unbound(guard: SqlGuard) -> None:
    """"segment" thuoc v_customer_segment, khong thuoc mart_application - du
    ca hai bang deu duoc phep, tron cot giua hai bang van la bia du lieu."""
    with pytest.raises(SQLUnboundIdentifier):
        guard.validate("SELECT segment FROM mart.mart_application")


# -----------------------------------------------------------------------------
# Cua 4: chi duoc cham schema mart
# -----------------------------------------------------------------------------

def test_raw_schema_is_blocked_with_correct_error_type(guard: SqlGuard) -> None:
    """Vi du dung dung trong docs/17 T12."""
    with pytest.raises(SQLSchemaNotAllowed):
        guard.validate("SELECT * FROM raw.fact_loan")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM raw.dim_customer",
    "SELECT * FROM ops.agent_trace",
    "SELECT * FROM mart.mart_application_not_in_allowlist",
    "SELECT * FROM public.mart_application",
])
def test_various_disallowed_schemas_and_tables_are_blocked(guard: SqlGuard, sql: str) -> None:
    with pytest.raises(SQLSchemaNotAllowed):
        guard.validate(sql)


def test_join_where_one_side_is_disallowed_is_blocked(guard: SqlGuard) -> None:
    with pytest.raises(SQLSchemaNotAllowed):
        guard.validate(
            "SELECT a.campaign_id FROM mart.mart_application a "
            "JOIN raw.fact_loan f ON a.campaign_id = f.campaign_id"
        )


# -----------------------------------------------------------------------------
# Cua 5: bat buoc co LIMIT
# -----------------------------------------------------------------------------

def test_missing_limit_is_auto_injected_with_default(guard: SqlGuard) -> None:
    """Vi du dung dung trong docs/17 T12: tu chen LIMIT 500."""
    result = guard.validate("SELECT campaign_id FROM mart.mart_application")
    assert result.ok
    assert result.limit_injected
    assert "LIMIT 500" in result.sql_rewritten


def test_existing_limit_under_max_is_kept_unchanged(guard: SqlGuard) -> None:
    result = guard.validate("SELECT campaign_id FROM mart.mart_application LIMIT 10")
    assert result.ok
    assert not result.limit_injected
    assert "LIMIT 10" in result.sql_rewritten


def test_existing_limit_over_max_is_clamped(guard: SqlGuard) -> None:
    result = guard.validate("SELECT campaign_id FROM mart.mart_application LIMIT 999999")
    assert result.ok
    assert "LIMIT 1000" in result.sql_rewritten
    assert "999999" not in result.sql_rewritten


# -----------------------------------------------------------------------------
# Cac ca THANH CONG khac (khong bi chan)
# -----------------------------------------------------------------------------

def test_star_select_on_allowed_table_passes(guard: SqlGuard) -> None:
    result = guard.validate("SELECT * FROM mart.mart_application")
    assert result.ok


def test_join_between_two_allowed_tables_passes(guard: SqlGuard) -> None:
    result = guard.validate(
        "SELECT a.campaign_id, d.channel FROM mart.mart_application a "
        "JOIN mart.dim_campaign d ON a.campaign_id = d.campaign_id LIMIT 100"
    )
    assert result.ok


def test_aggregation_with_group_by_on_real_columns_passes(guard: SqlGuard) -> None:
    result = guard.validate(
        "SELECT occupation, AVG(net_profit) FROM mart.mart_application "
        "GROUP BY occupation LIMIT 50"
    )
    assert result.ok


def test_where_clause_with_real_column_passes(guard: SqlGuard) -> None:
    result = guard.validate(
        "SELECT campaign_id FROM mart.mart_application WHERE romi < 0 LIMIT 10"
    )
    assert result.ok


def test_case_insensitive_keywords_and_identifiers_are_handled(guard: SqlGuard) -> None:
    result = guard.validate("select CAMPAIGN_ID from MART.mart_application limit 5")
    assert result.ok


def test_trailing_comment_does_not_block_a_valid_select(guard: SqlGuard) -> None:
    result = guard.validate("SELECT campaign_id FROM mart.mart_application -- ghi chu\nLIMIT 5")
    assert result.ok


# -----------------------------------------------------------------------------
# Loi cu phap
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "SELECT FROM WHERE campaign_id",
    "SELEC campaign_id FROM mart.mart_application",
    "SELECT campaign_id FROM (((",
])
def test_unparseable_sql_raises_parse_error(guard: SqlGuard, sql: str) -> None:
    with pytest.raises(SQLParseError):
        guard.validate(sql)


def test_empty_string_raises_forbidden_statement_not_crash(guard: SqlGuard) -> None:
    with pytest.raises((SQLParseError, SQLForbiddenStatement)):
        guard.validate("")


# -----------------------------------------------------------------------------
# Nap tu cau hinh playbook (config/playbooks/freeform.yml, protected)
# -----------------------------------------------------------------------------

def test_build_from_freeform_playbook_config_uses_its_allowed_tables() -> None:
    from app.agent.playbooks import get_playbook_store

    store = get_playbook_store()
    freeform = store.get("freeform")
    assert freeform.sql_guard is not None

    built = build_sql_guard_from_config(freeform.sql_guard, _SCHEMA)
    assert built._allowed_tables == _ALLOWED_TABLES  # type: ignore[attr-defined]

    with pytest.raises(SQLSchemaNotAllowed):
        built.validate("SELECT * FROM raw.fact_loan")

    result = built.validate("SELECT campaign_id FROM mart.mart_application")
    assert result.ok
