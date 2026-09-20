"""`/api/admin/*` - trang quan tri sua prompt + bang theo doi chat luong.
Xem docs/07-prompt-fewshot.md muc 7.5-7.6 va docs/09-api-ui.md.

BAT BUOC: khong co (hoac sai) header `X-Admin-Token` -> tra 404, KHONG PHAI
401 - khong duoc de lo su ton tai cua trang admin cho nguoi khong co token.

Luong sua prompt (docs 7.5-7.6): kiem tra (validate YAML) -> ghi ban CU vao
`ops.prompt_history` -> ghi ban MOI vao `ops.prompt_override` (nguon durable
qua redeploy) -> ghi de CHINH file `prompts/<id>.yaml` tren dia (PoC 1
replica - "đọc thẳng từ đĩa cũng đủ", docs 7.6 dong cuoi) de
`PromptLoader.get()` (da co san co che kiem tra mtime tu T07) nap lai NGAY
trong lan goi tiep theo - khong can co che poll rieng.
"""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy import text

from app.data.engines import get_engine_trace
from app.prompts.loader import DEFAULT_PROMPTS_DIR, PromptLoader
from app.settings import get_settings


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    """Depends() dung chung cho MOI route /api/admin/* - chay TRUOC khi
    FastAPI validate body cua route (dat o cap APIRouter), dam bao khong lo
    endpoint co ton tai qua ma loi 422 cho request thieu token."""
    expected = get_settings().admin.get("token")
    if not expected or x_admin_token != expected:
        # 404, KHONG PHAI 401 - xem docstring dau file.
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin_token)],
)


def _prompt_path(prompt_id: str) -> Path:
    path = DEFAULT_PROMPTS_DIR / f"{prompt_id}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not Found")
    return path


def _validate_yaml_content(prompt_id: str, content: str) -> list[str]:
    """Kiem tra NOI DUNG (chuoi) truoc khi ghi that - dung mot thu muc tam de
    tai su dung nguyen ven `PromptLoader.validate()` (T07) ma khong dung tay
    viet lai logic kiem tra. Tra ve danh sach loi (rong = hop le)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / f"{prompt_id}.yaml"
        tmp_path.write_text(content, encoding="utf-8")
        return PromptLoader(root=Path(tmp)).validate(prompt_id)


@router.post("/prompts/{prompt_id}/validate")
def validate_prompt(prompt_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Kiem tra CHUA GHI - dung cho nut "Kiem tra" tren UI truoc khi Luu that."""
    errors = _validate_yaml_content(prompt_id, str(body.get("content", "")))
    return {"valid": not errors, "errors": errors}


@router.get("/prompts")
def list_prompts() -> list[dict[str, Any]]:
    out = []
    for path in sorted(DEFAULT_PROMPTS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
        out.append({
            "id": data.get("id", path.stem), "version": data.get("version"),
            "model_role": data.get("model_role"), "updated_at": mtime.isoformat(),
        })
    return out


@router.get("/prompts/{prompt_id}")
def get_prompt(prompt_id: str) -> dict[str, Any]:
    path = _prompt_path(prompt_id)
    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}
    return {"id": prompt_id, "version": data.get("version"), "content": content}


@router.put("/prompts/{prompt_id}")
def update_prompt(prompt_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    path = _prompt_path(prompt_id)
    new_content = str(body.get("content", ""))
    updated_by = body.get("updated_by") or "admin"

    errors = _validate_yaml_content(prompt_id, new_content)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    new_data = yaml.safe_load(new_content) or {}
    old_content = path.read_text(encoding="utf-8")
    old_data = yaml.safe_load(old_content) or {}

    engine = get_engine_trace()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ops.prompt_history (prompt_id, version, content, created_by)
            VALUES (:prompt_id, :version, :content, :created_by)
        """), {
            "prompt_id": prompt_id, "version": old_data.get("version", ""),
            "content": old_content, "created_by": updated_by,
        })
        conn.execute(text("""
            INSERT INTO ops.prompt_override (prompt_id, version, content, updated_by)
            VALUES (:prompt_id, :version, :content, :updated_by)
            ON CONFLICT (prompt_id) DO UPDATE SET
                version = EXCLUDED.version, content = EXCLUDED.content,
                updated_at = now(), updated_by = EXCLUDED.updated_by
        """), {
            "prompt_id": prompt_id, "version": new_data.get("version", ""),
            "content": new_content, "updated_by": updated_by,
        })

    # PoC 1 replica: ghi thang xuong dia la du (docs 7.6) - PromptLoader.get()
    # tu phat hien mtime doi va nap lai NGAY o lan goi tiep theo.
    path.write_text(new_content, encoding="utf-8")

    return {"id": prompt_id, "version": new_data.get("version"), "saved": True}


@router.get("/quality")
def quality_daily() -> list[dict[str, Any]]:
    """Doc `ops.v_quality_daily` (etl/sql/03_ddl_ops.sql, protected) - xem
    docs/08-anti-hallucination.md muc 8.8."""
    engine = get_engine_trace()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM ops.v_quality_daily")).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["router"]
