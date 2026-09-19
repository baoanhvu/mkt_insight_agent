"""Bootstrap ha tang chi danh cho profile `test`.

TRAI: tren vDB RDS thuc (profile local/greennode), ba vai tro va ba schema
duoc tao MOT LAN bang tay, chay `psql "$ADMIN_URL" -f etl/sql/00_roles.sql`
voi mat khau thuc - dung nhu docs/03-database-choice.md muc 3.7 quy dinh.
Khong bao gio tu dong hoa buoc do cho DB dung chung, vi mat khau thuc phai
nam trong `config/secrets.yaml`, khong duoc sinh ra trong code.

PHAI: Postgres cuc bo trong docker-compose.dev.yml la mirror dung mot lan roi
bo, khong ai chay `psql` bang tay cho no truoc moi lan CI. Vi vay module nay
ap dung etl/sql/00_roles.sql voi mat khau CO DINH, CHI-DANH-CHO-TEST, va CHI
khi `settings.profile == "test"`. `ASSUMPTION`: config/profiles/test.yaml
(file protected) tro `database.url_admin` toi mkt_owner - script nay dung
dung URL do (da la superuser cua container Postgres) de tao ba vai tro.
"""

from __future__ import annotations

import psycopg

from etl.ddl_runner import run_sql_file

# Mat khau cuc bo, KHONG bao gio dung cho DB thuc. mkt_owner da ton tai (la
# POSTGRES_USER cua docker-compose.dev.yml) nen gia tri owner_pass khong duoc
# dung thuc te (nhanh CREATE ROLE cua no bi IF NOT EXISTS bo qua) - van phai
# co mat de thoa cu phap thay the bien cua psql trong file DDL.
TEST_ROLE_PASSWORDS: dict[str, str] = {
    "owner_pass": "devonly",
    "ro_pass": "test_ro_devonly",
    "trace_pass": "test_trace_devonly",
}


def bootstrap_test_roles(conn: psycopg.Connection) -> None:
    """Tao schema raw/mart/ops + ba vai tro (mkt_owner da co san). Idempotent -
    an toan goi lai nhieu lan (moi CREATE ROLE deu boc trong IF NOT EXISTS)."""
    run_sql_file(conn, "00_roles.sql", params=TEST_ROLE_PASSWORDS)


__all__ = ["bootstrap_test_roles", "TEST_ROLE_PASSWORDS"]
