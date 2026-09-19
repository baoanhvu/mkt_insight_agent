"""ETL buoc 3: chay DQ-01..09 + INV-1..7, ghi `ops.dq_result`.

Nguon dinh nghia: docs/02-data-model.md muc 2.5. Muc `BLOCK` fail -> ETL dung
(exit code 1) va agent tu choi phuc vu (readiness probe doc `ops.v_blocking_dq`
- xem etl/sql/03_ddl_ops.sql). Muc `WARN`/`INFO` chi ghi lai, khong chan.

DQ-08 (ten cot Excel lech hop dong) da duoc `etl/load_excel.py` chan NGAY tai
luc doc, truoc khi du lieu nao kip vao raw - o day chi ghi lai la da qua vong
kiem do.

CLI:
    python -m etl.dq_checks
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import psycopg

from app.logging_ import get_logger
from app.settings import get_settings
from etl.dsn import to_libpq_url

log = get_logger(__name__)

Severity = str  # "INFO" | "WARN" | "BLOCK"


@dataclass(frozen=True, slots=True)
class CheckSpec:
    check_id: str
    severity: Severity
    description_vi: str
    sql_query: str          # tra ve DUNG MOT dong, MOT hoac nhieu cot
    expected: dict[str, Any] | None  # None = tu tinh passed trong sql_query (cot 'passed')


CHECKS: tuple[CheckSpec, ...] = (
    # -------------------------------------------------------------------
    # DQ-01..09 - INFO/WARN, ghi lai profile du lieu da biet
    # -------------------------------------------------------------------
    CheckSpec(
        "DQ-01", "WARN",
        "disbursement_date som hon create_at",
        "SELECT COUNT(*) AS observed FROM mart.mart_application WHERE dq_flag_date_order",
        {"observed": 6},
    ),
    CheckSpec(
        "DQ-02", "WARN",
        "form_filling_time <= 0 (da chuyen NULL trong mart)",
        "SELECT COUNT(*) AS observed FROM raw.fact_digital_footprint WHERE form_filling_time <= 0",
        {"observed": 9},
    ),
    CheckSpec(
        "DQ-03", "WARN",
        "toan bo giao dich chi nam trong mot thang (chan phat bieu lien thang/YoY)",
        "SELECT COUNT(DISTINCT create_at::date) AS observed FROM raw.fact_loan",
        {"observed": 31},
    ),
    CheckSpec(
        "DQ-04", "INFO",
        "fact_lead khong co khoa ngoai toi fact_loan (cau noi la sub_channel). "
        "fact_lead VAN co FK toi dim_customer - do la binh thuong, chi khong co FK toi fact_loan",
        "SELECT COUNT(*) AS observed FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON ccu.constraint_name = tc.constraint_name "
        "  AND ccu.constraint_schema = tc.constraint_schema "
        "WHERE tc.table_schema = 'raw' AND tc.table_name = 'fact_lead' "
        "AND tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'fact_loan'",
        {"observed": 0},
    ),
    CheckSpec(
        "DQ-05", "INFO",
        "fact_lead.customer_id NULL (chi chien dich tai vay co gia tri)",
        "SELECT COUNT(*) AS observed FROM raw.fact_lead WHERE customer_id IS NULL",
        {"observed": 13116},
    ),
    CheckSpec(
        "DQ-06", "INFO",
        "ho so tu choi co loan_amount/tenure deu NULL (dung nghiep vu)",
        "SELECT COUNT(*) AS observed FROM raw.fact_loan "
        "WHERE loan_amount IS NULL AND tenure IS NULL",
        {"observed": 1062},
    ),
    CheckSpec(
        "DQ-07", "INFO",
        "khach hang chua co ho so nao (doi tuong cua khuyen nghi D3)",
        "SELECT COUNT(*) AS observed FROM mart.mart_customer_value WHERE is_never_applied",
        {"observed": 347},
    ),
    CheckSpec(
        "DQ-08", "BLOCK",
        "ten cot Excel khop hop dong (da chan tai etl/load_excel.py truoc khi toi day)",
        "SELECT true AS passed",
        None,
    ),
    CheckSpec(
        "DQ-09", "INFO",
        "loan_balance khac loan_amount (khach da tra bot, khong dung lan hai cot). "
        "Dinh nghia khop docs/02 muc 2.5: NULL tinh la 'khac' (kieu pandas != trong "
        "profiling goc), khac voi SQL 'IS DISTINCT FROM' coi NULL=NULL la KHONG khac "
        "- vi vay dung OR ro rang thay vi IS DISTINCT FROM (chi ra 157, thieu 1062 "
        "ho so tu choi ca hai cot deu NULL)",
        "SELECT COUNT(*) AS observed FROM raw.fact_loan "
        "WHERE loan_balance IS NULL OR loan_amount IS NULL OR loan_balance != loan_amount",
        {"observed": 1219},
    ),
    # -------------------------------------------------------------------
    # INV-1..7 - BLOCK, bat bien cau truc THAT (khong phai profile mo ta)
    # -------------------------------------------------------------------
    CheckSpec(
        "INV-1", "BLOCK",
        "application_id dong nhat giua fact_loan, loan_application_pnl, fact_digital_footprint",
        """
        SELECT (
            (SELECT COUNT(*) FROM raw.fact_loan l
             FULL JOIN raw.loan_application_pnl p ON p.loan_application_id = l.application_id
             WHERE l.application_id IS NULL OR p.loan_application_id IS NULL) = 0
            AND
            (SELECT COUNT(*) FROM raw.fact_loan l
             FULL JOIN raw.fact_digital_footprint d ON d.loan_application_id = l.application_id
             WHERE l.application_id IS NULL OR d.loan_application_id IS NULL) = 0
        ) AS passed
        """,
        None,
    ),
    CheckSpec(
        "INV-2", "BLOCK",
        "REJECTED va DISBURSED loai trui nhau",
        "SELECT COUNT(*) = 0 AS passed FROM mart.mart_application "
        "WHERE is_rejected AND is_disbursed",
        None,
    ),
    CheckSpec(
        "INV-3", "BLOCK",
        "rejected + disbursed = tong so ho so (1062 + 1625 = 2687)",
        "SELECT "
        "(COUNT(*) FILTER (WHERE is_rejected)) + (COUNT(*) FILTER (WHERE is_disbursed)) "
        "= COUNT(*) AS passed "
        "FROM mart.mart_application",
        None,
    ),
    CheckSpec(
        "INV-4", "BLOCK",
        "moi customer_id trong fact_loan ton tai trong dim_customer",
        "SELECT COUNT(*) = 0 AS passed FROM raw.fact_loan l "
        "LEFT JOIN raw.dim_customer c ON c.customer_id = l.customer_id "
        "WHERE c.customer_id IS NULL",
        None,
    ),
    CheckSpec(
        "INV-5", "BLOCK",
        "moi sub_channel trong fact_loan co trong dim_campaign",
        "SELECT COUNT(*) = 0 AS passed FROM raw.fact_loan l "
        "LEFT JOIN mart.dim_campaign c ON c.sub_channel = l.sub_channel "
        "WHERE c.sub_channel IS NULL",
        None,
    ),
    CheckSpec(
        "INV-6", "BLOCK",
        "ho so bi tu choi co tong doanh thu bang 0",
        "SELECT COUNT(*) = 0 AS passed FROM mart.mart_application "
        "WHERE is_rejected AND total_revenue != 0",
        None,
    ),
    CheckSpec(
        "INV-7", "BLOCK",
        "mart_application co dung so dong bang raw.fact_loan (join khong nhan dong)",
        "SELECT "
        "(SELECT COUNT(*) FROM mart.mart_application) = (SELECT COUNT(*) FROM raw.fact_loan) "
        "AS passed",
        None,
    ),
)


def _latest_ok_run_id(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(run_id) FROM ops.etl_run WHERE status = 'OK'")
        row = cur.fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(
            "chua co etl_run thanh cong nao - chay 'python -m etl.load_excel' truoc"
        )
    return int(row[0])


def _run_one_check(conn: psycopg.Connection, spec: CheckSpec) -> tuple[bool, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(spec.sql_query)  # noi bo, khong phai input nguoi dung
        columns = [d.name for d in cur.description or []]
        row = cur.fetchone()
    observed = dict(zip(columns, row, strict=True)) if row else {}

    if spec.expected is not None:
        passed = observed == spec.expected
    else:
        passed = bool(observed.get("passed", False))
    return passed, observed


def run_all_checks() -> list[dict[str, Any]]:
    """Chay toan bo CHECKS, ghi vao ops.dq_result, tra ve danh sach ket qua.

    Returns:
        Danh sach dict {check_id, severity, passed, observed} - dung de CLI in
        bang tong ket va de test doi chieu.

    Raises:
        RuntimeError: chua co etl_run 'OK' nao (chua chay load_excel).
    """
    settings = get_settings()
    admin_url = to_libpq_url(settings.database.get("url_admin", settings.database.url))

    results: list[dict[str, Any]] = []
    with psycopg.connect(admin_url, autocommit=False) as conn:
        run_id = _latest_ok_run_id(conn)

        for spec in CHECKS:
            passed, observed = _run_one_check(conn, spec)
            results.append(
                {
                    "check_id": spec.check_id,
                    "severity": spec.severity,
                    "passed": passed,
                    "observed": observed,
                }
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ops.dq_result (run_id, check_id, severity, passed, observed)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, check_id)
                    DO UPDATE SET severity = EXCLUDED.severity,
                                  passed = EXCLUDED.passed,
                                  observed = EXCLUDED.observed,
                                  checked_at = now()
                    """,
                    (run_id, spec.check_id, spec.severity, passed, _to_jsonb(observed)),
                )
        conn.commit()
        log.info("dq_checks_done", run_id=run_id, n_checks=len(results))

    return results


def _to_jsonb(observed: dict[str, Any]) -> Any:
    import json

    return json.dumps(observed, default=str)


def main(argv: list[str] | None = None) -> int:
    try:
        results = run_all_checks()
    except Exception as exc:
        print(f"LOI DQ CHECKS: {exc}", file=sys.stderr)
        return 1

    print(f"{'check_id':<8} {'severity':<6} {'passed':<7} observed")
    blocking_failures = []
    for r in results:
        print(f"{r['check_id']:<8} {r['severity']:<6} {r['passed']!s:<7} {r['observed']}")
        if r["severity"] == "BLOCK" and not r["passed"]:
            blocking_failures.append(r["check_id"])

    if blocking_failures:
        print(f"\nBLOCK: {', '.join(blocking_failures)} FAIL - ETL bi chan.", file=sys.stderr)
        return 1

    print("\nKhong co muc BLOCK nao fail.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
