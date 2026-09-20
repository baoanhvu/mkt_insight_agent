"""`create_app()` - diem lap rap DUY NHAT: router, static, template, middleware.

Xem docs/11-module-spec.md muc 11.1. Goi tu `main.py` (entrypoint AgentBase).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes_actions import router as actions_router
from app.api.routes_chat import router as chat_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_health import router as health_router
from app.api.routes_segments import router as segments_router
from app.settings import get_settings

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=str(settings.app.get("name", "Marketing Insight Agent")),
        docs_url="/api/docs", redoc_url=None,
    )

    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(segments_router)
    app.include_router(actions_router)
    app.include_router(chat_router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        ui = settings.ui
        return templates.TemplateResponse(
            request, "index.html",
            {
                "app_name": settings.app.get("name", "Marketing Insight Agent"),
                "tabs": list(ui.get("tabs", ["campaign", "persona", "actions", "chat"])),
                "default_tab": ui.get("default_tab", "campaign"),
            },
        )

    return app


__all__ = ["create_app", "WEB_DIR"]
