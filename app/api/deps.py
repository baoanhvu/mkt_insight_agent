"""Dependency injection cho FastAPI routes.

Moi provider deu dung lai singleton da cache (`get_catalog()`, `get_engine_ro()`
...) - khong tao moi tren tung request, vi engine giu connection pool.
"""

from __future__ import annotations

from functools import lru_cache

from app.data.repository import SqlMetricRunner
from app.semantic.catalog import YamlCatalog, get_catalog
from app.semantic.compiler import MetricCompiler


def get_catalog_dep() -> YamlCatalog:
    return get_catalog()


def get_compiler_dep() -> MetricCompiler:
    return MetricCompiler(get_catalog())


@lru_cache(maxsize=1)
def get_metric_runner() -> SqlMetricRunner:
    return SqlMetricRunner(catalog=get_catalog())


__all__ = ["get_catalog_dep", "get_compiler_dep", "get_metric_runner"]
