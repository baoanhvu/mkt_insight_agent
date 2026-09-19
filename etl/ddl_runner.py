"""Thuc thi cac file .sql trong etl/sql/ mot cach an toan tren Postgres thuc.

QUY TAC QUAN TRONG: `etl/sql/*.sql` la file **da kiem chung, khong duoc viet
lai** (xem CLAUDE.md). Module nay KHONG chua logic DDL nao ca - no chi tach
mot file .sql thanh danh sach cau lenh roi thuc thi nguyen van tung cau. Neu
DDL can sua, sua trong file .sql; khong "vong qua" bang cach chep logic vao
day.

Ham `substitute_psql_vars` thay cu phap bien `:'ten'` cua `psql` (dung trong
etl/sql/00_roles.sql) bang gia tri chuoi. Tham so nay LUON la hang so noi bo
do chinh etl/ tu tao ra (mat khau test cuc bo) - khong bao gio la du lieu
nguoi dung, nen khong vi pham R2 (khong noi du lieu nguoi dung vao SQL).
"""

from __future__ import annotations

import re
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "etl" / "sql"

_PSQL_VAR = re.compile(r":'(\w+)'")


def split_statements(sql_text: str) -> list[str]:
    """Tach mot khoi SQL thanh danh sach cau lenh.

    Xu ly ca ba truong hop cung mot luc, vi chung anh huong nhau:
      - `-- ...` ket thuc o cuoi dong, KE CA khi dung sau ma tren cung dong
        (vi du "tenure SMALLINT, -- thang; NULL khi bi tu choi" - dau ';' o
        trong comment nay KHONG duoc tinh la ket thuc cau lenh).
      - Chuoi ky tu `'...'` (bao gom '' de thoat mot dau nhay) - dau ';' hay
        `$$` nam trong chuoi khong duoc tinh.
      - Khoi `$$ ... $$` (dung trong `DO $$ ... END $$;` cua 00_roles.sql) -
        dau ';' nam trong khoi nay khong ket thuc cau lenh.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False
    in_string = False
    i, n = 0, len(sql_text)
    while i < n:
        two = sql_text[i : i + 2]
        if not in_string and not in_dollar and two == "--":
            nl = sql_text.find("\n", i)
            if nl == -1:
                break
            buf.append("\n")
            i = nl + 1
            continue
        if not in_dollar and sql_text[i] == "'":
            in_string = not in_string
            buf.append("'")
            i += 1
            continue
        if not in_string and two == "$$":
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = sql_text[i]
        if ch == ";" and not in_dollar and not in_string:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def substitute_psql_vars(sql_text: str, params: dict[str, str]) -> str:
    """Thay `:'ten'` bang gia tri da escape don trong `params['ten']`."""

    def _replace(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in params:
            raise KeyError(f"thieu tham so psql ':{name}' khi thuc thi DDL")
        return "'" + params[name].replace("'", "''") + "'"

    return _PSQL_VAR.sub(_replace, sql_text)


def run_sql_file(
    conn: psycopg.Connection,
    filename: str,
    params: dict[str, str] | None = None,
    skip_prefixes: tuple[str, ...] = (),
) -> None:
    """Thuc thi tung cau lenh trong `etl/sql/{filename}` tren connection da mo.

    Khong tu commit - goi noi dung goi `conn.commit()` khi xong, de nhieu file
    DDL chay duoc trong cung mot transaction khi can.
    """
    text = (SQL_DIR / filename).read_text(encoding="utf-8")
    if params:
        text = substitute_psql_vars(text, params)
    cur = conn.cursor()
    for stmt in split_statements(text):
        head = " ".join(stmt.split()).upper()
        if any(head.startswith(p) for p in skip_prefixes):
            continue
        try:
            cur.execute(stmt)  # DDL noi bo, khong phai input nguoi dung
        except Exception as exc:
            raise RuntimeError(
                f"{filename}: cau lenh loi:\n  {stmt[:200]}\n  -> {exc}"
            ) from exc


__all__ = ["run_sql_file", "split_statements", "substitute_psql_vars", "SQL_DIR"]
