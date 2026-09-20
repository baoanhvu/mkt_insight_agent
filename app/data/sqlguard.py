"""L0/L1 - SQL guard cho duong freeform (docs/05-semantic-layer.md muc 5.6,
7 cua kiem tra; config/playbooks/freeform.yml, protected, la nguon su that
DUY NHAT cho allowed_tables/default_limit/max_limit). Kiem tra TREN CAY CU
PHAP (sqlglot), khong tren chuoi - so khop chuoi bi danh bai boi comment,
hoa/thuong va cau truc long nhau.

Nam trong app/data/ (khong phai app/verify/) vi day la lop DUY NHAT trong
"kiem chung" can biet schema THAT cua DB - R3 cam app/verify/ dung app.data,
nen ranh gioi module dat sqlguard o day, tach voi L2-L4 (von thuan tuy, chi
doc EvidenceSet, khong biet gi ve DB that).

Trien khai `app.contracts.SQLGuard`. `validate()` RAISE mot trong cac loi
`SQLGuardError` (app/errors.py) ngay khi bi chan - day la quy uoc chung cua
toan bo codebase (xem UnknownMetricError, MissingEntityError...), khong tra
ve doi tuong trang thai loi rieng.
"""

from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from app.contracts import GuardResult
from app.errors import (
    SQLForbiddenStatement,
    SQLParseError,
    SQLSchemaNotAllowed,
    SQLUnboundIdentifier,
)

# {schema: {table: {column: kieu_du_lieu}}} - dinh dang ma sqlglot.optimizer mong doi.
TableSchema = dict[str, dict[str, dict[str, str]]]


def _table_key(table: exp.Table) -> str:
    schema = (table.db or "").lower()
    name = table.name.lower()
    return f"{schema}.{name}" if schema else name


class SqlGuard:
    """Trien khai `app.contracts.SQLGuard`."""

    def __init__(
        self, table_schema: TableSchema, allowed_tables: frozenset[str],
        *, default_limit: int = 500, max_limit: int = 1000, dialect: str = "postgres",
    ) -> None:
        self._schema = table_schema
        self._allowed_tables = allowed_tables
        self._default_limit = default_limit
        self._max_limit = max_limit
        self._dialect = dialect

    def validate(self, sql: str) -> GuardResult:
        stmt = self._parse_single_select(sql)

        for table in stmt.find_all(exp.Table):
            key = _table_key(table)
            if key not in self._allowed_tables:
                raise SQLSchemaNotAllowed(
                    f"truy vấn chạm tới bảng không được phép: '{key}'", sql=sql, table=key,
                )

        try:
            qualified = qualify(
                stmt.copy(), schema=self._schema, dialect=self._dialect,
                validate_qualify_columns=True, identify=False,
            )
        except OptimizeError as exc:
            raise SQLUnboundIdentifier(str(exc), sql=sql) from exc
        except ParseError as exc:  # phong thu: qualify co the parse lai noi bo
            raise SQLParseError(str(exc), sql=sql) from exc
        assert isinstance(qualified, exp.Select)  # qualify() tren mot Select luon tra ve Select

        qualified, limit_injected = self._enforce_limit(qualified)
        return GuardResult(
            ok=True, sql_rewritten=qualified.sql(dialect=self._dialect),
            limit_injected=limit_injected,
        )

    def _parse_single_select(self, sql: str) -> exp.Select:
        try:
            parsed = [s for s in sqlglot.parse(sql, dialect=self._dialect) if s is not None]
        except ParseError as exc:
            raise SQLParseError(str(exc), sql=sql) from exc

        if len(parsed) != 1:
            raise SQLForbiddenStatement(
                f"chỉ cho phép ĐÚNG MỘT câu lệnh, tìm thấy {len(parsed)}", sql=sql,
            )
        stmt = parsed[0]
        if not isinstance(stmt, exp.Select):
            raise SQLForbiddenStatement(
                f"chỉ cho phép SELECT, tìm thấy câu lệnh kiểu '{type(stmt).__name__}'", sql=sql,
            )
        return stmt

    def _enforce_limit(self, stmt: exp.Select) -> tuple[exp.Select, bool]:
        """Bat buoc co LIMIT (chen `default_limit` neu thieu); cap ve
        `max_limit` neu LIMIT co san vuot qua."""
        existing = stmt.args.get("limit")
        if existing is None:
            return stmt.limit(self._default_limit), True

        try:
            n = int(existing.expression.this)
        except (AttributeError, ValueError, TypeError):
            return stmt, False
        if n > self._max_limit:
            return stmt.limit(self._max_limit), False
        return stmt, False

    async def explain(self, sql: str) -> dict[str, Any]:
        """Cua thu 6: EXPLAIN chay duoi CHINH role `mkt_agent_ro` - bat loi
        kieu/chi phi truoc khi quet that. Import tri hoan de validate() khong
        bao gio can ket noi DB (dung duoc trong unit test thuan)."""
        from sqlalchemy import text

        from app.data.engines import get_engine_ro

        with get_engine_ro().connect() as conn:
            rows = conn.execute(text(f"EXPLAIN (FORMAT JSON) {sql}")).all()
        return {"plan": rows[0][0] if rows else None}


def build_table_schema_from_db(engine: Any, allowed_tables: frozenset[str]) -> TableSchema:
    """Doc schema THAT tu `information_schema.columns` cho dung cac bang
    trong `allowed_tables` - dung LUC KHOI DONG ung dung (mot lan, cache o
    tang goi - xem app/agent/tools/sql_tool.py), KHONG dung trong unit test
    (tests/test_sqlguard.py tu dung mot schema tinh, khong can DB)."""
    from sqlalchemy import text

    schema: TableSchema = {}
    with engine.connect() as conn:
        for full in allowed_tables:
            schema_name, _, table_name = full.partition(".")
            rows = conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name = :table"
                ),
                {"schema": schema_name, "table": table_name},
            ).all()
            if rows:
                schema.setdefault(schema_name, {})[table_name] = {r[0]: r[1] for r in rows}
    return schema


def build_sql_guard_from_config(cfg: dict[str, Any], table_schema: TableSchema) -> SqlGuard:
    """`cfg` la `playbook.sql_guard` (tu config/playbooks/freeform.yml,
    protected) - nguon su that DUY NHAT cho allowed_tables/default_limit/
    max_limit, khong hardcode lai o day de tranh troi lech."""
    allowed_tables = frozenset(t.lower() for t in cfg.get("allowed_tables", ()))
    return SqlGuard(
        table_schema=table_schema, allowed_tables=allowed_tables,
        default_limit=int(cfg.get("default_limit", 500)),
        max_limit=int(cfg.get("max_limit", 1000)),
    )


__all__ = [
    "SqlGuard", "TableSchema", "build_table_schema_from_db", "build_sql_guard_from_config",
]
