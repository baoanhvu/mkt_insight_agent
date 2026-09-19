"""`/health` va `/readyz` TACH RIENG - xem docs/09-api-ui.md muc 9.1.

`/health` CHI khang dinh process con song, KHONG cham DB - AgentBase Runtime
dung no de quyet dinh ACTIVE; neu cho no fail khi mat DB, runtime co the bi
khoi dong lai lien tuc trong khi van de nam o database, khong o container.

`/readyz` moi noi "co phuc vu duoc cau tra loi dung hay khong": DB noi duoc,
khong co muc DQ nao o muc BLOCK dang fail, catalog nap thanh cong.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.api.schemas import HealthResponse, ReadyResponse, VersionResponse
from app.data.engines import get_engine_ro
from app.errors import CatalogValidationError
from app.semantic.catalog import get_catalog
from app.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
def readyz(response: Response) -> ReadyResponse:
    db_status: str = "ok"
    dq_status: str = "unknown"
    catalog_status: str = "ok"
    detail_parts: list[str] = []

    try:
        with get_engine_ro().connect() as conn:
            conn.execute(text("SELECT 1"))
            blocking = conn.execute(text("SELECT check_id FROM ops.v_blocking_dq")).all()
        dq_status = "blocked" if blocking else "ok"
        if blocking:
            detail_parts.append(f"DQ BLOCK dang fail: {[r[0] for r in blocking]}")
    except Exception as exc:
        db_status = "error"
        detail_parts.append(f"loi ket noi DB: {exc}")

    try:
        get_catalog()
    except (CatalogValidationError, OSError) as exc:
        catalog_status = "error"
        detail_parts.append(f"loi nap catalog: {exc}")

    overall_ok = db_status == "ok" and dq_status == "ok" and catalog_status == "ok"
    if not overall_ok:
        response.status_code = 503

    return ReadyResponse(
        status="ok" if overall_ok else "degraded",
        db=db_status,  # type: ignore[arg-type]
        dq=dq_status,  # type: ignore[arg-type]
        catalog=catalog_status,  # type: ignore[arg-type]
        detail="; ".join(detail_parts) or None,
    )


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    settings = get_settings()
    catalog = get_catalog()
    return VersionResponse(
        app=str(settings.app.get("name", "Marketing Insight Agent")),
        profile=settings.profile,
        metrics_version=catalog.version,
    )


__all__ = ["router"]
