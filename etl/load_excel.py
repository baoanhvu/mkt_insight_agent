"""ETL buoc 1: nap Excel/parquet nguyen trang vao schema `raw`.

Lam ba viec, THEO DUNG THU TU (docs/02-data-model.md muc 2.6):
  1. Chuan hoa ten cot ve snake_case va **ASSERT** khop `COLUMN_CONTRACT`
     (DQ-08, muc BLOCK). Excel co 6 cot viet hoa/thuong lan: `Customer_id`
     (fact_lead, fact_loan), `Age`, `Customer_open_date` (dim_customer),
     `Processing_Fee`, `Partner_Fee`, `Collection_Cost` (loan_application_pnl).
     Voi bo du lieu nay, ha thuong toan bo ten cot la du de chuan hoa dung.
  2. Ep kieu ve dung kieu cot cua `etl/sql/01_ddl_raw.sql` (chu yeu la cot
     ngay: pandas doc chung tu Excel co the ra float64 toan NaN khi mau rong).
  3. Nap vao schema `raw` trong MOT transaction bang COPY, idempotent: moi
     lan chay DROP+CREATE lai bang tu chinh etl/sql/01_ddl_raw.sql (khong
     TRUNCATE tho, vi vay schema luon dung tuyet doi voi DDL that).

CLI:
    python -m etl.load_excel --source excel
    python -m etl.load_excel --source parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg import sql

from app.logging_ import get_logger
from app.settings import get_settings
from etl.bootstrap_infra import bootstrap_test_roles
from etl.ddl_runner import run_sql_file
from etl.dsn import to_libpq_url

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
EXCEL_PATH = ROOT / "data" / "full_schema_mock_v2.xlsx"
PARQUET_DIR = ROOT / "data" / "parquet"

# Thu tu nap: PHAI theo chieu khoa ngoai (cha truoc con), khop DROP nguoc lai
# trong etl/sql/01_ddl_raw.sql.
LOAD_ORDER: tuple[str, ...] = (
    "dim_customer", "fact_lead", "fact_loan",
    "fact_reject", "loan_application_pnl", "fact_digital_footprint",
)

# Hop dong cot = dung etl/sql/01_ddl_raw.sql, DUNG THU TU (COPY doc theo vi tri).
COLUMN_CONTRACT: dict[str, tuple[str, ...]] = {
    "dim_customer": (
        "customer_id", "age", "customer_open_date", "occupation",
        "active_status", "has_app", "income",
    ),
    "fact_lead": (
        "lead_id", "customer_id", "partner_code", "channel", "sub_channel",
        "create_at", "product_id", "campaign_id", "campaign_name",
        "utm_source", "utm_medium",
    ),
    "fact_loan": (
        "application_id", "customer_id", "product_id", "product_name",
        "create_at", "disbursement_date", "settlement_date", "partner_code",
        "channel", "sub_channel", "tenure", "no_paid", "last_duedate",
        "last_dayslate", "max_dayslate", "nominal_interest_rate",
        "loan_amount", "loan_number_rank", "loan_balance",
    ),
    "fact_reject": ("loan_application_id", "reason_level_1", "reason_level_2"),
    "loan_application_pnl": (
        "loan_application_id", "interest_income", "overdue_interest",
        "early_paid_off_fee", "processing_fee", "loan_processing_cost",
        "funding_cost", "lead_cost", "credit_loss", "operation_cost",
        "marketing_cost", "partner_fee", "collection_cost",
    ),
    "fact_digital_footprint": (
        "loan_application_id", "device_os", "device_price_segment",
        "form_filling_time", "ip_address", "geo_location_match",
    ),
}

# Cot can ep ve TIMESTAMP. Cac cot khac giu kieu pandas da suy ra - psycopg
# dump dung int/float/bool/None/str khi COPY dang van ban.
DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "dim_customer": ("customer_open_date",),
    "fact_lead": ("create_at",),
    "fact_loan": ("create_at", "disbursement_date", "settlement_date", "last_duedate"),
}

# Cot SMALLINT/BIGINT nullable ma pandas doc thanh float64 vi co NaN (ho so tu
# choi - DQ-06). "6.0" khong phai literal SMALLINT hop le trong Postgres, nen
# phai ep ve kieu Int64 (nullable) cua pandas TRUOC khi COPY.
INT_COLUMNS: dict[str, tuple[str, ...]] = {
    "fact_loan": ("tenure", "no_paid", "last_dayslate", "max_dayslate",
                   "loan_amount", "loan_balance"),
}

EXPECTED_ROWS: dict[str, int] = {
    "dim_customer": 2901, "fact_lead": 14530, "fact_loan": 2687,
    "fact_reject": 1062, "loan_application_pnl": 2687, "fact_digital_footprint": 2687,
}


class ColumnContractError(RuntimeError):
    """DQ-08 (muc BLOCK): ten cot Excel khong khop hop dong. Dung ETL ngay."""


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """DQ-08: ha ten cot ve snake_case. Voi bo du lieu nay, ha thuong toan bo
    la du (xem 6 cot le^ch o docstring dau file)."""
    return df.rename(columns={c: c.lower() for c in df.columns})


def _assert_column_contract(sheet: str, df: pd.DataFrame) -> None:
    expected = set(COLUMN_CONTRACT[sheet])
    actual = set(df.columns)
    if actual != expected:
        raise ColumnContractError(
            f"DQ-08 BLOCK: sheet '{sheet}' lech hop dong cot - "
            f"thieu={sorted(expected - actual)} thua={sorted(actual - expected)}"
        )


def _cast_dates(sheet: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in DATE_COLUMNS.get(sheet, ()):
        df[col] = pd.to_datetime(df[col])
    for col in INT_COLUMNS.get(sheet, ()):
        df[col] = df[col].astype("Int64")
    return df


def read_sheet(source: str, sheet: str) -> pd.DataFrame:
    """Doc mot sheet, chuan hoa cot, assert hop dong, ep kieu ngay, va tra ve
    dung THU TU cot cua COLUMN_CONTRACT (COPY doc theo vi tri, khong theo ten)."""
    if source == "excel":
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet)
    elif source == "parquet":
        df = pd.read_parquet(PARQUET_DIR / sheet)
    else:
        raise ValueError(f"source khong hop le: {source!r}")
    df = _normalize_columns(df)
    _assert_column_contract(sheet, df)
    df = _cast_dates(sheet, df)
    return df[list(COLUMN_CONTRACT[sheet])]


def _pyval(v: Any) -> Any:
    """Chuyen mot gia tri pandas/numpy don ve kieu Python thuan; NaN/NaT/None
    deu tra None (Postgres NULL).

    `pd.isna()` kiem tra ca ba dang thieu du lieu (None, float NaN, pd.NaT) -
    kiem tra rieng tung dang (nhu ban dau) bo lot NaT vi `pd.NaT` KHONG phai
    instance cua `pd.Timestamp`, khien no lot qua thanh chuoi "NaT" khi COPY.
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass  # gia tri khong ho tro isna (hiem, vi du numpy array) - bo qua
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if hasattr(v, "item"):  # numpy scalar: int64, float64, bool_...
        return v.item()
    return v


def _copy_dataframe(conn: psycopg.Connection, sheet: str, df: pd.DataFrame) -> int:
    cols = COLUMN_CONTRACT[sheet]
    col_ident = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
    stmt = sql.SQL("COPY raw.{table} ({cols}) FROM STDIN").format(
        table=sql.Identifier(sheet), cols=col_ident
    )
    n = 0
    with conn.cursor() as cur, cur.copy(stmt) as copy:
        for row in df.itertuples(index=False, name=None):
            copy.write_row(tuple(_pyval(v) for v in row))
            n += 1
    return n


def _start_etl_run(conn: psycopg.Connection, source: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ops.etl_run (source, status) VALUES (%s, 'RUNNING') "
            "RETURNING run_id",
            (source,),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _finish_etl_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    rows_loaded: dict[str, int],
    error_message: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ops.etl_run SET finished_at = now(), status = %s, "
            "rows_loaded = %s, error_message = %s WHERE run_id = %s",
            (status, json.dumps(rows_loaded), error_message, run_id),
        )
    conn.commit()


def load_all(source: str = "excel") -> dict[str, int]:
    """Nap toan bo 6 sheet vao schema raw. Tra ve so dong da nap theo bang.

    Raises:
        ColumnContractError: DQ-08 - ten cot Excel lech hop dong.
        RuntimeError: so dong nap khac EXPECTED_ROWS, hoac mot cau DDL loi.
    """
    settings = get_settings()
    admin_url = to_libpq_url(settings.database.get("url_admin", settings.database.url))
    rows_loaded: dict[str, int] = {}

    with psycopg.connect(admin_url, autocommit=False) as conn:
        for schema in ("raw", "mart", "ops"):
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.commit()

        if settings.profile == "test":
            bootstrap_test_roles(conn)
            conn.commit()

        # ops.etl_run/dq_result phai ton tai TRUOC khi ta ghi run dau tien.
        run_sql_file(conn, "03_ddl_ops.sql")
        conn.commit()

        run_id = _start_etl_run(conn, source)
        conn.commit()
        log.info("etl_run_started", run_id=run_id, source=source)

        try:
            run_sql_file(conn, "01_ddl_raw.sql")  # DROP+CREATE - luon dung DDL that
            conn.commit()

            for sheet in LOAD_ORDER:
                df = read_sheet(source, sheet)
                n = _copy_dataframe(conn, sheet, df)
                rows_loaded[sheet] = n
                if EXPECTED_ROWS[sheet] != n:
                    raise RuntimeError(
                        f"sheet '{sheet}': nap {n} dong, ky vong {EXPECTED_ROWS[sheet]}"
                    )
                log.info("sheet_loaded", sheet=sheet, rows=n)

            conn.commit()
            _finish_etl_run(conn, run_id, "OK", rows_loaded, None)
            log.info("etl_run_ok", run_id=run_id, rows_loaded=rows_loaded)
        except Exception as exc:
            conn.rollback()
            _finish_etl_run(conn, run_id, "FAILED", rows_loaded, str(exc))
            log.error("etl_run_failed", run_id=run_id, error=str(exc))
            raise

    return rows_loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nap Excel/parquet vao schema raw")
    parser.add_argument("--source", choices=["excel", "parquet"], default="excel")
    args = parser.parse_args(argv)

    try:
        rows = load_all(source=args.source)
    except Exception as exc:
        print(f"LOI ETL: {exc}", file=sys.stderr)
        return 1

    print("Nap raw thanh cong:")
    for sheet, n in rows.items():
        print(f"  raw.{sheet:<24} {n:>6} dong")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
