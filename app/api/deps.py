"""Dependency injection cho FastAPI routes.

Moi provider deu dung lai singleton da cache (`get_catalog()`, `get_engine_ro()`
...) - khong tao moi tren tung request, vi engine giu connection pool.
"""

from __future__ import annotations

from functools import lru_cache

from app.agent.orchestrator import Orchestrator, build_orchestrator
from app.data.repository import SqlMetricRunner
from app.semantic.catalog import YamlCatalog, get_catalog
from app.semantic.compiler import MetricCompiler
from app.telemetry.store import PgTraceStore


def get_catalog_dep() -> YamlCatalog:
    return get_catalog()


def get_compiler_dep() -> MetricCompiler:
    return MetricCompiler(get_catalog())


@lru_cache(maxsize=1)
def get_metric_runner() -> SqlMetricRunner:
    return SqlMetricRunner(catalog=get_catalog())


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    """Singleton cho ca tien trinh - QUAN TRONG: `LLMClient` giu token bucket
    (8 req/phut, xem app/llm/client.py) phai dung CHUNG giua moi request HTTP,
    khong duoc tao moi tren tung cau hoi, neu khong tran 10 RPM cua ca tai
    khoan MaaS se bi vo hieu hoa."""
    return build_orchestrator()


@lru_cache(maxsize=1)
def get_trace_store() -> PgTraceStore:
    return PgTraceStore()


__all__ = [
    "get_catalog_dep", "get_compiler_dep", "get_metric_runner", "get_orchestrator",
    "get_trace_store",
]
