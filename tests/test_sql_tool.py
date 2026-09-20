"""Kiem tra app/agent/tools/sql_tool.py::SqlTool - vong sinh SQL + sua loi.
Khong nam trong "Xong khi" bat buoc cua T12 (chi test_sqlguard.py), nhung
cong cu nay can Postgres THAT de chay truy van - dung cung fixture-skip nhu
tests/test_orchestrator.py.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.agent.tools.sql_tool import SqlTool
from app.data.sqlguard import SqlGuard, build_table_schema_from_db
from app.errors import SQLRepairExhausted
from app.prompts.loader import PromptLoader
from app.settings import get_settings

_ALLOWED_TABLES = frozenset({"mart.mart_application"})


class FakeLLM:
    """Tra ve lan luot tung phan tu cua `responses` - dung mo phong LLM sua
    loi qua nhieu vong (lan dau sai, lan sau dung)."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        self.calls.append(messages)
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]

    async def stream(self, messages: list[dict[str, str]], **kwargs: object) -> AsyncIterator[str]:
        yield await self.complete(messages)


def _skip_if_unreachable() -> None:
    try:
        engine = create_engine(get_settings().database.url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


@pytest.fixture
def guard() -> SqlGuard:
    _skip_if_unreachable()
    engine = create_engine(get_settings().database.url)
    schema = build_table_schema_from_db(engine, _ALLOWED_TABLES)
    return SqlGuard(schema, _ALLOWED_TABLES, default_limit=500, max_limit=1000)


@pytest.fixture
def prompts() -> PromptLoader:
    return PromptLoader()


async def test_valid_sql_on_first_try_executes_and_returns_fact(
    guard: SqlGuard, prompts: PromptLoader,
) -> None:
    response = json.dumps({"sql": "SELECT campaign_id, net_profit FROM mart.mart_application LIMIT 5"})
    llm = FakeLLM([response])
    tool = SqlTool(guard, llm, prompts)

    fact = await tool.run("Cho tôi 5 chiến dịch bất kỳ", fact_id="F1")

    assert fact.fact_id == "F1"
    assert fact.row_count == 5
    assert len(llm.calls) == 1
    assert all(row.get("_ref") for row in fact.rows)


async def test_blocked_sql_triggers_repair_then_succeeds(
    guard: SqlGuard, prompts: PromptLoader,
) -> None:
    """Lan dau bia cot khong ton tai (bi SqlGuard chan) -> tool phai gui lai
    thong tin loi va thu lan hai, lan nay dung."""
    bad = json.dumps({"sql": "SELECT cot_bia_ra FROM mart.mart_application LIMIT 5"})
    good = json.dumps({"sql": "SELECT campaign_id FROM mart.mart_application LIMIT 5"})
    llm = FakeLLM([bad, good])
    tool = SqlTool(guard, llm, prompts, max_repair_attempts=3)

    fact = await tool.run("Một câu hỏi bất kỳ", fact_id="F1")

    assert fact.row_count == 5
    assert len(llm.calls) == 2
    # Vong sua loi phai keo thong tin loi vao tin nhan lan hai.
    assert any("bị chặn" in m.get("content", "") for m in llm.calls[1])


async def test_repeated_failures_raise_repair_exhausted(
    guard: SqlGuard, prompts: PromptLoader,
) -> None:
    always_bad = json.dumps({"sql": "SELECT * FROM raw.fact_loan"})
    llm = FakeLLM([always_bad])
    tool = SqlTool(guard, llm, prompts, max_repair_attempts=2)

    with pytest.raises(SQLRepairExhausted):
        await tool.run("Một câu hỏi bất kỳ", fact_id="F1")
    assert len(llm.calls) == 2


async def test_non_json_response_raises_repair_exhausted(
    guard: SqlGuard, prompts: PromptLoader,
) -> None:
    llm = FakeLLM(["đây không phải JSON"])
    tool = SqlTool(guard, llm, prompts, max_repair_attempts=1)

    with pytest.raises(SQLRepairExhausted):
        await tool.run("Một câu hỏi bất kỳ", fact_id="F1")
