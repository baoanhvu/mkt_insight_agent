"""Tien ich chuyen doi chuoi ket noi.

`app/settings.py` luu URL theo dang SQLAlchemy (`postgresql+psycopg://...`) vi
do la quy uoc chung cua du an (xem docs/10-config-secrets.md). `psycopg` (driver
dung truc tiep trong etl/, khong qua SQLAlchemy) chi hieu dang libpq thuan
(`postgresql://...`), nen can boc lai truoc khi `psycopg.connect()`.
"""

from __future__ import annotations


def to_libpq_url(url: str) -> str:
    """`postgresql+psycopg://...` -> `postgresql://...`. Giu nguyen neu da la
    dang libpq (khong co hau to driver)."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


__all__ = ["to_libpq_url"]
