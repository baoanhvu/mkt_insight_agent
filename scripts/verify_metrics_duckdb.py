"""Doi chieu tung chi so trong metrics.yml voi du lieu that. KHONG CAN DATABASE.

Script dung lai schema mart tren DuckDB trong bo nho, bang cach doc CHINH file
etl/sql/02_ddl_mart.sql - nen no khong the troi khoi DDL that. Sau do no chay
tung bieu thuc SQL trong config/semantic/metrics.yml va so voi khoi `reference`.

    python scripts/verify_metrics_duckdb.py
    python scripts/verify_metrics_duckdb.py --metric romi     # chi mot chi so
    python scripts/verify_metrics_duckdb.py --verbose         # in ca ca dat

Exit code 0 = moi gia tri khop. Khac 0 = co lech.

Vi sao ton tai: mot agent-developer moi vao can kiem chung dinh nghia chi so
NGAY NGAY DAU, truoc khi co Postgres. Khong co buoc nay thi loi mau so hay loi
join se di xa truoc khi bi phat hien.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXCEL = ROOT / "data" / "full_schema_mock_v2.xlsx"
MART_DDL = ROOT / "etl" / "sql" / "02_ddl_mart.sql"

# Ten cot Excel -> snake_case. Phai khop etl/load_excel.py -> COLUMN_CONTRACT.
RENAME = {
    "fact_lead": {"Customer_id": "customer_id"},
    "fact_loan": {"Customer_id": "customer_id"},
    "dim_customer": {"Age": "age", "Customer_open_date": "customer_open_date"},
    "loan_application_pnl": {"Processing_Fee": "processing_fee",
                             "Partner_Fee": "partner_fee",
                             "Collection_Cost": "collection_cost"},
}

# Cac cau lenh Postgres ma DuckDB khong co. Chung khong anh huong toi ket qua
# chi so, chi anh huong toi rang buoc va quyen - nen bo qua duoc mot cach an toan.
SKIP_PREFIXES = ("ALTER TABLE", "COMMENT ON", "GRANT", "ANALYZE", "CREATE INDEX",
                 "CREATE UNIQUE INDEX")

# Khoa trong khoi `reference` -> (bo loc, chieu gom nhom)
REF_SHAPES: dict[str, tuple[str | None, str | None]] = {
    "total":            (None, None),
    "all_customers":    (None, None),
    "among_applied":    ("n_applications > 0", None),
    "by_campaign":      (None, "campaign_id"),
    "by_income_band":   ("n_applications > 0", "income_band"),
    "by_age_band":      ("n_applications > 0", "age_band"),
    "by_has_app":       ("n_applications > 0", "has_app"),
    "by_segment":       (None, "segment"),
    "by_is_repeat_customer": ("n_applications > 0", "is_repeat_customer"),
    "by_reason_level_1": ("is_rejected", "reason_level_1"),
    "by_geo_location_match": (None, "geo_location_match"),
    "by_device_os":     (None, "device_os"),
    "by_is_repeat_loan": (None, "is_repeat_loan"),
}


def build_db() -> duckdb.DuckDBPyConnection:
    """Nap Excel vao schema raw, roi chay CHINH file DDL mart."""
    con = duckdb.connect()
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE SCHEMA IF NOT EXISTS mart")

    xl = pd.ExcelFile(EXCEL)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet).rename(columns=RENAME.get(sheet, {}))
        con.register(f"_tmp_{sheet}", df)
        con.execute(f"CREATE TABLE raw.{sheet} AS SELECT * FROM _tmp_{sheet}")

    sql = MART_DDL.read_text(encoding="utf-8")
    sql = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)      # bo comment dong
    for stmt in (s.strip() for s in sql.split(";")):
        if not stmt:
            continue
        head = " ".join(stmt.split()).upper()
        if head.startswith(SKIP_PREFIXES):
            continue
        try:
            con.execute(stmt)
        except Exception as exc:
            print(f"  LOI khi chay DDL:\n    {stmt[:110]}...\n    -> {exc}")
            raise
    return con


def fmt(v: object) -> str:
    if isinstance(v, float):
        return f"{v:,.4f}" if abs(v) < 100 else f"{v:,.0f}"
    return str(v)


def tolerance(unit: str, expected: float) -> float:
    if unit in ("ratio", "percent"):
        return 0.002
    if unit == "count":
        return 0.5
    return max(abs(expected) * 0.001, 1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metric", help="chi kiem tra mot chi so")
    ap.add_argument("--verbose", action="store_true", help="in ca cac ca dat")
    args = ap.parse_args()

    entities = yaml.safe_load((ROOT / "config/semantic/entities.yml").read_text(encoding="utf-8"))
    mdoc = yaml.safe_load((ROOT / "config/semantic/metrics.yml").read_text(encoding="utf-8"))
    datasets = entities["datasets"]
    dimensions = entities["dimensions"]
    metrics = mdoc["metrics"]

    print("=" * 76)
    print("DOI CHIEU CHI SO VOI DU LIEU THAT  (DuckDB, khong can Postgres)")
    print(f"  DDL:      {MART_DDL.relative_to(ROOT)}")
    print(f"  Catalog:  config/semantic/metrics.yml  v{mdoc['version']}")
    print("=" * 76)

    con = build_db()
    for t in ("mart_application", "mart_customer_value", "mart_campaign_daily"):
        n = con.sql(f"SELECT COUNT(*) FROM mart.{t}").fetchone()[0]
        exp = {"mart_application": 2687, "mart_customer_value": 2901,
               "mart_campaign_daily": 186}[t]
        flag = "OK " if n == exp else "SAI"
        print(f"  {flag} mart.{t:22s} {n:6d}  (ky vong {exp})")
    print()

    n_ok = n_fail = n_skip = 0
    failures: list[str] = []

    for mname, m in metrics.items():
        if args.metric and mname != args.metric:
            continue
        if not isinstance(m, dict) or "reference" not in m or "sql" not in m:
            continue

        ds = datasets.get(m.get("dataset", ""), None)
        if ds is None:
            continue
        table = ds["table"]
        unit = m.get("unit", "count")

        for key, expected in (m["reference"] or {}).items():
            if key not in REF_SHAPES:
                n_skip += 1
                continue
            where, groupby = REF_SHAPES[key]

            # Chieu gom nhom phai ton tai trong dataset cua chi so nay
            if groupby:
                dim = dimensions.get(groupby)
                if dim is None or m.get("dataset") not in dim.get("datasets", []):
                    n_skip += 1
                    continue

            sel = f"({m['sql']}) AS v"
            sql = f"SELECT {groupby + ', ' if groupby else ''}{sel} FROM {table}"
            if where:
                sql += f" WHERE {where}"
            if groupby:
                sql += f" GROUP BY {groupby}"

            try:
                df = con.sql(sql).df()
            except Exception as exc:
                n_fail += 1
                failures.append(f"{mname}.{key}: SQL loi -> {str(exc)[:90]}")
                continue

            if groupby is None:
                got = df["v"].iloc[0]
                tol = tolerance(unit, float(expected))
                if got is None or abs(float(got) - float(expected)) > tol:
                    n_fail += 1
                    failures.append(
                        f"{mname}.{key}: duoc {fmt(got)} ky vong {fmt(expected)}")
                else:
                    n_ok += 1
                    if args.verbose:
                        print(f"  OK  {mname}.{key} = {fmt(got)}")
                continue

            lookup = {str(r[groupby]).lower(): r["v"] for _, r in df.iterrows()}
            for bucket, exp_val in (expected or {}).items():
                got = lookup.get(str(bucket).lower())
                if got is None:
                    n_fail += 1
                    failures.append(f"{mname}.{key}[{bucket}]: khong co trong ket qua")
                    continue
                tol = tolerance(unit, float(exp_val))
                if abs(float(got) - float(exp_val)) > tol:
                    n_fail += 1
                    failures.append(
                        f"{mname}.{key}[{bucket}]: duoc {fmt(got)} ky vong {fmt(exp_val)}")
                else:
                    n_ok += 1
                    if args.verbose:
                        print(f"  OK  {mname}.{key}[{bucket}] = {fmt(got)}")

    if failures:
        print("LECH:")
        for f in failures:
            print(f"  SAI  {f}")
        print()

    print("=" * 76)
    print(f"KET QUA: {n_ok} khop | {n_fail} lech | {n_skip} bo qua (dang reference chua ho tro)")
    print("=" * 76)
    if n_fail:
        print("\nMot gia tri lech nghia la DINH NGHIA CHI SO hoac DDL sai,")
        print("KHONG phai khoi `reference` sai. Dung sua `reference` de lam xanh.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
