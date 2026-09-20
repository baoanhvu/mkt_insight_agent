"""Kiem tra POST /invocations - cong khong streaming (docs/15 muc 15.9,
docs/12-build-deploy.md muc 12.7). Can Postgres cua profile test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.settings import get_settings


def _skip_if_unreachable() -> None:
    try:
        engine = create_engine(get_settings().database.url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


@pytest.fixture
def client() -> TestClient:
    _skip_if_unreachable()
    from app.api.app_factory import create_app

    return TestClient(create_app())


def test_invocations_returns_answer_markdown_evidence_and_trust(client: TestClient) -> None:
    """BAT BUOC (docs/12 muc 12.7 checklist): tra ve answer_markdown +
    evidence + trust."""
    res = client.post("/invocations", json={"message": "Chiến dịch nào đang lỗ?"})
    assert res.status_code == 200, res.text
    data = res.json()

    assert "trace_id" in data
    assert "answer_markdown" in data
    assert isinstance(data["evidence"], list) and len(data["evidence"]) > 0
    assert data["trust"] is not None
    assert "score" in data["trust"] and "band" in data["trust"]
    assert data["meta"]["llm_calls"] <= 2


def test_invocations_out_of_scope_question_still_returns_200(client: TestClient) -> None:
    res = client.post("/invocations", json={"message": "Thời tiết Hà Nội hôm nay thế nào?"})
    assert res.status_code == 200
    data = res.json()
    assert data["evidence"] == []
