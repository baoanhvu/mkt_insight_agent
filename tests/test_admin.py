"""Kiem tra app/api/routes_admin.py - T13. Xem docs/17 T13.

BAT BUOC:
    /api/admin/* khong co (hoac sai) X-Admin-Token -> 404, KHONG PHAI 401.
    Co token dung -> GET /api/admin/prompts tra ve danh sach prompt.
    Sua prompt qua PUT -> ghi ops.prompt_history, PromptLoader nap lai ngay
    (khong can doi > 5s vi ghi thang xuong dia - xem docstring routes_admin.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.settings import clear_settings_cache, get_settings

_TOKEN = "test-admin-token-xyz"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MKT_ADMIN__TOKEN", _TOKEN)
    clear_settings_cache()
    from app.api.app_factory import create_app

    app = create_app()
    try:
        yield TestClient(app)
    finally:
        clear_settings_cache()


def _skip_if_db_unreachable() -> None:
    try:
        engine = create_engine(get_settings().database.url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(f"Postgres test khong san sang: {exc}")


def test_missing_token_returns_404_not_401(client: TestClient) -> None:
    """Vi du dung dung trong docs/17 T13."""
    res = client.get("/api/admin/prompts")
    assert res.status_code == 404


def test_wrong_token_also_returns_404(client: TestClient) -> None:
    res = client.get("/api/admin/prompts", headers={"X-Admin-Token": "sai-token"})
    assert res.status_code == 404


@pytest.mark.parametrize("path", [
    "/api/admin/prompts", "/api/admin/prompts/route_intent", "/api/admin/quality",
])
def test_every_admin_endpoint_requires_token(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_correct_token_lists_all_prompts(client: TestClient) -> None:
    """Vi du dung dung trong docs/17 T13: tra ve danh sach do dai = so file
    trong prompts/ (10 sau khi them generate_sql.yaml o T12)."""
    res = client.get("/api/admin/prompts", headers={"X-Admin-Token": _TOKEN})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 9
    assert {"id", "version", "model_role", "updated_at"} <= data[0].keys()


def test_get_single_prompt_returns_raw_yaml_content(client: TestClient) -> None:
    res = client.get("/api/admin/prompts/route_intent", headers={"X-Admin-Token": _TOKEN})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "route_intent"
    assert "system:" in data["content"] or "instructions:" in data["content"]


def test_get_unknown_prompt_id_returns_404(client: TestClient) -> None:
    res = client.get("/api/admin/prompts/khong_ton_tai", headers={"X-Admin-Token": _TOKEN})
    assert res.status_code == 404


def test_validate_endpoint_accepts_valid_and_rejects_broken_yaml(client: TestClient) -> None:
    good = client.post(
        "/api/admin/prompts/route_intent/validate",
        headers={"X-Admin-Token": _TOKEN},
        json={"content": "id: route_intent\nversion: \"1.0.0\"\nmodel_role: router\nsystem: |\n  x\ninstructions: |\n  y\n"},
    )
    assert good.status_code == 200
    assert good.json()["valid"] is True

    bad = client.post(
        "/api/admin/prompts/route_intent/validate",
        headers={"X-Admin-Token": _TOKEN},
        json={"content": "id: [khong dong ngoac"},
    )
    assert bad.status_code == 200
    assert bad.json()["valid"] is False
    assert bad.json()["errors"]


def test_save_prompt_writes_history_and_reloads_within_5s(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """BAT BUOC (docs/17 T13): sua prompt qua UI -> reload < 5s, ghi
    ops.prompt_history. Dung mot BAN SAO cua clarify_question.yaml trong
    thu muc tam (monkeypatch DEFAULT_PROMPTS_DIR cua routes_admin) - KHONG
    BAO GIO ghi truc tiep vao prompts/ that (file protected, xem CLAUDE.md)."""
    _skip_if_db_unreachable()
    import shutil
    import time

    from app.api import routes_admin
    from app.prompts.loader import DEFAULT_PROMPTS_DIR, PromptLoader

    prompt_id = "clarify_question"
    shutil.copy(DEFAULT_PROMPTS_DIR / f"{prompt_id}.yaml", tmp_path / f"{prompt_id}.yaml")
    monkeypatch.setattr(routes_admin, "DEFAULT_PROMPTS_DIR", tmp_path)

    original = (tmp_path / f"{prompt_id}.yaml").read_text(encoding="utf-8")
    new_content = original.replace('version: "1.0.0"', 'version: "1.0.1"')
    assert new_content != original, "fixture gia dinh version hien tai la 1.0.0"

    engine = create_engine(get_settings().database.url)
    with engine.connect() as conn:
        before = conn.execute(
            text("SELECT COUNT(*) FROM ops.prompt_history WHERE prompt_id = :p"),
            {"p": prompt_id},
        ).scalar()

    res = client.put(
        f"/api/admin/prompts/{prompt_id}",
        headers={"X-Admin-Token": _TOKEN}, json={"content": new_content},
    )
    assert res.status_code == 200, res.text
    assert res.json()["version"] == "1.0.1"

    with engine.connect() as conn:
        after = conn.execute(
            text("SELECT COUNT(*) FROM ops.prompt_history WHERE prompt_id = :p"),
            {"p": prompt_id},
        ).scalar()
    assert after == before + 1

    t0 = time.monotonic()
    loader = PromptLoader(root=tmp_path)
    reloaded = loader.get(prompt_id)
    assert reloaded["version"] == "1.0.1"
    assert time.monotonic() - t0 < 5.0
