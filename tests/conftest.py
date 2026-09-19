"""Fixture dung chung cho toan bo test.

`mart_db` dung ban sao mart tren DuckDB tu Excel + DDL that (etl/duckdb_mirror.py).
Nho vay tests/test_metrics_contract.py chay duoc NGAY, khong can Postgres, khong can
docker - mot agent-developer moi vao kiem chung duoc dinh nghia chi so tu ngay dau.

Khi nhiem vu T04 xong, bo sung mot fixture `mart_pg` chay tren Postgres va
parametrize test_metrics_contract theo ca hai. Hai engine phai cho cung ket qua.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from etl.duckdb_mirror import build_mart_db, check_row_counts  # noqa: E402


@pytest.fixture(scope="session")
def mart_db() -> Iterator[Any]:
    """Ban sao mart tren DuckDB. Chi dung mot lan cho ca phien test."""
    con = build_mart_db(source="excel")
    yield con
    con.close()


@pytest.fixture(scope="session")
def catalog() -> dict[str, Any]:
    """config/semantic/metrics.yml da parse."""
    return yaml.safe_load(
        (ROOT / "config/semantic/metrics.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def entities() -> dict[str, Any]:
    """config/semantic/entities.yml da parse."""
    return yaml.safe_load(
        (ROOT / "config/semantic/entities.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def analytics_cfg() -> dict[str, Any]:
    """config/analytics.yaml da parse."""
    return yaml.safe_load(
        (ROOT / "config/analytics.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def verify_cfg() -> dict[str, Any]:
    """config/verify.yaml da parse."""
    return yaml.safe_load(
        (ROOT / "config/verify.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def golden_set() -> dict[str, Any]:
    """evals/golden/qa_set.yaml da parse."""
    return yaml.safe_load(
        (ROOT / "evals/golden/qa_set.yaml").read_text(encoding="utf-8"))


def pytest_report_header(config: pytest.Config) -> list[str]:  # noqa: ARG001
    return ["mart_db: DuckDB mirror tu data/full_schema_mock_v2.xlsx + etl/sql/02_ddl_mart.sql"]


__all__ = ["mart_db", "catalog", "entities", "analytics_cfg", "verify_cfg",
           "golden_set", "check_row_counts"]
