"""ETL buoc 2: dung `mart.dim_campaign` + ba mart tu schema `raw`.

Chi thuc thi nguyen van `etl/sql/02_ddl_mart.sql` (da kiem chung tren du lieu
that - xem CLAUDE.md). Khong chua logic transform nao o day; sua mart thi sua
file .sql, khong sua module nay.

CLI:
    python -m etl.build_marts
"""

from __future__ import annotations

import sys

import psycopg

from app.logging_ import get_logger
from app.settings import get_settings
from etl.ddl_runner import run_sql_file
from etl.dsn import to_libpq_url

log = get_logger(__name__)

ROW_COUNT_CHECKS: dict[str, int] = {
    "mart.dim_campaign": 6,
    "mart.mart_application": 2687,
    "mart.mart_customer_value": 2901,
    "mart.mart_campaign_daily": 186,
}


def build_marts() -> dict[str, int]:
    """Chay 02_ddl_mart.sql roi doi chieu so dong voi gia tri da biet.

    Returns:
        So dong thuc te tung bang mart, de CLI in ra va de test doi chieu.

    Raises:
        RuntimeError: mot bang mart ra so dong khac ky vong - dau hieu JOIN sai
        (vi du join nham cot lam nhan dong, hoac fact_loan.sub_channel khong
        khop het mart.dim_campaign - xem INV-5/INV-7 trong etl/dq_checks.py).
    """
    settings = get_settings()
    admin_url = to_libpq_url(settings.database.get("url_admin", settings.database.url))

    with psycopg.connect(admin_url, autocommit=False) as conn:
        run_sql_file(conn, "02_ddl_mart.sql")
        conn.commit()

        counts: dict[str, int] = {}
        with conn.cursor() as cur:
            for table, expected in ROW_COUNT_CHECKS.items():
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                row = cur.fetchone()
                assert row is not None
                got = int(row[0])
                counts[table] = got
                if got != expected:
                    raise RuntimeError(
                        f"{table}: {got} dong, ky vong {expected} - kiem tra JOIN trong "
                        f"etl/sql/02_ddl_mart.sql (co the fact_loan.sub_channel khong "
                        f"khop het dim_campaign, xem INV-5/INV-7)"
                    )
        log.info("marts_built", counts=counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    try:
        counts = build_marts()
    except Exception as exc:
        print(f"LOI BUILD MART: {exc}", file=sys.stderr)
        return 1

    print("Dung mart thanh cong:")
    for table, n in counts.items():
        print(f"  {table:<28} {n:>6} dong")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
