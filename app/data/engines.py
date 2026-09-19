"""Ba SQLAlchemy Engine tach biet theo vai tro (docs/03-database-choice.md muc 3.3).

KHONG dung chung mot pool cho ca ba viec - do la chinh rao chan, khong phai su
tien loi:

  engine_ro     mkt_agent_ro   MOI truy van phuc vu cau tra loi (metric tool,
                                sql tool). Role nay co default_transaction_read_only
                                = on dat o MUC DATABASE (etl/sql/00_roles.sql) -
                                ke ca code sai, Postgres van tu choi ghi.
  engine_trace  mkt_trace_rw   Chi INSERT/SELECT/UPDATE vao schema ops.
  engine_admin  mkt_owner      CHI dung trong script etl/. KHONG BAO GIO goi
                                trong app/api, app/agent hay app/data/repository.py.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.errors import ReadOnlyViolation
from app.settings import get_settings

# SQLSTATE 25006 = read_only_sql_transaction, 42501 = insufficient_privilege.
# Ca hai deu la "Postgres tu choi ghi" - dung bat ky cai nao trong so nay lam
# minh chung role chi-doc con hieu luc.
_READ_ONLY_SQLSTATES = frozenset({"25006", "42501"})

_PROBE_INSERT = text(
    "INSERT INTO mart.dim_campaign "
    "(sub_channel, campaign_id, campaign_name, channel, partner_code, "
    "product_id, utm_source, utm_medium) "
    "VALUES ('__probe__', '__probe__', '__probe__', '__probe__', '__probe__', "
    "'__probe__', '__probe__', '__probe__')"
)


@lru_cache(maxsize=1)
def get_engine_ro() -> Engine:
    """mkt_agent_ro - moi truy van phuc vu cau tra loi di qua day."""
    s = get_settings()
    return create_engine(
        s.database.url,
        pool_size=int(s.database.get("pool_size", 5)),
        max_overflow=int(s.database.get("max_overflow", 5)),
        pool_pre_ping=True,
        pool_recycle=int(s.database.get("pool_recycle_s", 1800)),
    )


@lru_cache(maxsize=1)
def get_engine_trace() -> Engine:
    """mkt_trace_rw - chi INSERT/SELECT/UPDATE vao schema ops."""
    s = get_settings()
    url = s.database.get("url_trace", s.database.url)
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_engine_admin() -> Engine:
    """mkt_owner - CHI dung trong script etl/. Khong goi ham nay trong
    duong dan phuc vu request thong thuong."""
    s = get_settings()
    url = s.database.get("url_admin", s.database.url)
    return create_engine(url, pool_pre_ping=True)


class _ProbeSucceededUnexpectedly(Exception):
    """Sentinel noi bo: nem ben trong `conn.begin()` de BAT BUOC rollback ke
    ca khi INSERT thanh cong - phep thu nay khong bao gio duoc phep de lai
    du lieu, bat ke ket qua dung hay sai."""


def assert_read_only_role(engine: Engine) -> None:
    """Thu INSERT bang `engine` da cho, KY VONG nhan loi tu chinh Postgres.

    Day la phep thu chay o luc khoi dong ung dung (readiness), khong phai chi
    la unit test: neu no PASS ma khong raise nghia la rao chan da mat va agent
    co the ghi du lieu that qua duong tra loi cau hoi - dung server ngay.

    Raises:
        ReadOnlyViolation: INSERT thanh cong (dung khong ngo toi) - LOI LAP
            TRINH nghiem trong, dieu tra ngay theo docs cua ReadOnlyViolation.
        DBAPIError: mot loi khac (khong phai read-only) - de lo ra ngoai vi no
            khong chung minh duoc dieu ta muon kiem tra.
    """
    try:
        with engine.connect() as conn, conn.begin():
            conn.execute(_PROBE_INSERT)
            raise _ProbeSucceededUnexpectedly()  # bat buoc rollback truoc khi raise ra ngoai
    except _ProbeSucceededUnexpectedly:
        raise ReadOnlyViolation(
            "role chi-doc van INSERT thanh cong - rao chan DB da mat, "
            "dieu tra ngay truoc khi phuc vu bat ky request nao"
        ) from None
    except DBAPIError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate in _READ_ONLY_SQLSTATES:
            return
        raise


def dispose_all_engines() -> None:
    """Dong toan bo connection pool va xoa cache factory. Dung khi tat ung
    dung sach se hoac giua cac test doi profile."""
    for factory in (get_engine_ro, get_engine_trace, get_engine_admin):
        if factory.cache_info().currsize:
            factory().dispose()
        factory.cache_clear()


__all__ = [
    "get_engine_ro", "get_engine_trace", "get_engine_admin",
    "assert_read_only_role", "dispose_all_engines",
]
