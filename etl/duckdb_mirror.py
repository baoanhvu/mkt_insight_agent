"""Dung ban sao schema mart tren DuckDB trong bo nho, tu Excel + DDL that.

Dung o hai noi:
  - scripts/verify_metrics_duckdb.py  : doi chieu chi so, khong can Postgres
  - tests/conftest.py                 : fixture `mart_db` cho unit test

VI SAO TON TAI: mot agent-developer moi vao phai kiem chung duoc dinh nghia chi so
NGAY NGAY DAU, truoc khi dung Postgres. Khong co buoc nay thi loi mau so hay loi
join se di rat xa truoc khi bi phat hien.

BAT BIEN: module nay doc CHINH file etl/sql/02_ddl_mart.sql, khong chep lai logic.
Nho vay ban sao khong the troi khoi DDL that.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

ROOT = Path(__file__).resolve().parent.parent
EXCEL = ROOT / "data" / "full_schema_mock_v2.xlsx"
PARQUET = ROOT / "data" / "parquet"
MART_DDL = ROOT / "etl" / "sql" / "02_ddl_mart.sql"

# Ten cot Excel -> snake_case. PHAI khop etl/load_excel.py -> COLUMN_CONTRACT.
RENAME: dict[str, dict[str, str]] = {
    "fact_lead": {"Customer_id": "customer_id"},
    "fact_loan": {"Customer_id": "customer_id"},
    "dim_customer": {"Age": "age", "Customer_open_date": "customer_open_date"},
    "loan_application_pnl": {
        "Processing_Fee": "processing_fee",
        "Partner_Fee": "partner_fee",
        "Collection_Cost": "collection_cost",
    },
}

# Cau lenh Postgres ma DuckDB khong co. Chung khong anh huong toi KET QUA chi so,
# chi anh huong toi rang buoc va quyen - nen bo qua duoc mot cach an toan.
SKIP_PREFIXES = (
    "ALTER TABLE", "COMMENT ON", "GRANT", "ANALYZE",
    "CREATE INDEX", "CREATE UNIQUE INDEX",
)

EXPECTED_ROWS = {
    "raw.dim_customer": 2901,
    "raw.fact_lead": 14530,
    "raw.fact_loan": 2687,
    "raw.fact_reject": 1062,
    "raw.loan_application_pnl": 2687,
    "raw.fact_digital_footprint": 2687,
    "mart.dim_campaign": 6,
    "mart.mart_application": 2687,
    "mart.mart_customer_value": 2901,
    "mart.mart_campaign_daily": 186,
}


def build_mart_db(source: str = "excel") -> "duckdb.DuckDBPyConnection":
    """Nap du lieu vao schema raw roi chay CHINH file DDL mart.

    Args:
        source: "excel" hoac "parquet".

    Raises:
        RuntimeError: neu mot cau DDL that bai, kem cau lenh gay loi.
    """
    import duckdb
    import pandas as pd

    con = duckdb.connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE SCHEMA IF NOT EXISTS mart")

    if source == "excel":
        xl = pd.ExcelFile(EXCEL)
        for sheet in xl.sheet_names:
            df = xl.parse(sheet).rename(columns=RENAME.get(sheet, {}))
            con.register(f"_tmp_{sheet}", df)
            con.execute(f"CREATE TABLE raw.{sheet} AS SELECT * FROM _tmp_{sheet}")
    elif source == "parquet":
        for d in sorted(PARQUET.iterdir()):
            if d.is_dir():
                con.execute(
                    f"CREATE TABLE raw.{d.name} AS "
                    f"SELECT * FROM read_parquet('{d.as_posix()}/**/*.parquet', "
                    f"hive_partitioning=true)"
                )
    else:
        raise ValueError(f"source khong hop le: {source!r}")

    sql = MART_DDL.read_text(encoding="utf-8")
    sql = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)
    for stmt in (s.strip() for s in sql.split(";")):
        if not stmt:
            continue
        if " ".join(stmt.split()).upper().startswith(SKIP_PREFIXES):
            continue
        try:
            con.execute(stmt)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"DDL that bai:\n  {stmt[:160]}...\n  -> {exc}"
            ) from exc
    return con


def check_row_counts(con: "duckdb.DuckDBPyConnection") -> list[str]:
    """Doi chieu so dong voi EXPECTED_ROWS. Tra ve danh sach lech (rong = dat)."""
    out: list[str] = []
    for table, expected in EXPECTED_ROWS.items():
        got = con.sql(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if got != expected:
            out.append(f"{table}: {got} dong, ky vong {expected}")
    return out
