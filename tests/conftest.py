"""Fixture dung chung cho toan bo test.

`mart_db` dung ban sao mart tren DuckDB tu Excel + DDL that (etl/duckdb_mirror.py).
Nho vay tests/test_metrics_contract.py chay duoc NGAY, khong can Postgres, khong can
docker - mot agent-developer moi vao kiem chung duoc dinh nghia chi so tu ngay dau.

Khi nhiem vu T04 xong, bo sung mot fixture `mart_pg` chay tren Postgres va
parametrize test_metrics_contract theo ca hai. Hai engine phai cho cung ket qua.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# tests/e2e/ (Playwright) khong nam trong `pytest tests/ -q` mac dinh: no khoi
# dong mot tien trinh main.py rieng + trinh duyet Chromium, va chay xen voi
# hang tram test tich hop DB khac trong CUNG mot phien de gay tranh chap tai
# nguyen tren may phat trien (da quan sat: 2 test cuoi trong
# test_ui_chat_height.py timeout khi chay chung, nhung 5/5 on dinh khi chay
# rieng). Chay e2e bang lenh rieng: pytest tests/e2e -q
collect_ignore = ["e2e"]

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


def pytest_report_header(config: pytest.Config) -> list[str]:
    return ["mart_db: DuckDB mirror tu data/full_schema_mock_v2.xlsx + etl/sql/02_ddl_mart.sql"]


__all__ = ["mart_db", "catalog", "entities", "analytics_cfg", "verify_cfg",
           "golden_set", "check_row_counts"]
