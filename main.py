"""Entrypoint AgentBase. Ten file BAT BUOC la `main.py` (docs/12-build-deploy.md
muc 12.2). Hai yeu cau CUNG cua runtime (muc 12.3): lang nghe cong 8080, va
`GET /health` tra 200 - ca hai duoc thoa boi `app.api.app_factory.create_app()`.
"""

from __future__ import annotations

from dotenv import load_dotenv

# Nap .env NEU CO (dev/deploy cuc bo, xem .env.example) TRUOC khi doc settings -
# khong lam gi neu file khong ton tai (vi du trong container: .dockerignore
# khong COPY .env vao image, AgentBase Runtime tiem bien moi truong truc tiep).
# Khong ghi de bien da co san trong moi truong (mac dinh cua load_dotenv).
load_dotenv()

from app.logging_ import configure_logging, get_logger  # noqa: E402 - phai load_dotenv truoc
from app.settings import get_settings  # noqa: E402

_settings = get_settings()
configure_logging(_settings)
_log = get_logger(__name__)

from app.api.app_factory import create_app  # noqa: E402 - phai cau hinh log truoc

app = create_app()


def main() -> None:
    import uvicorn

    host = str(_settings.app.get("host", "0.0.0.0"))
    port = int(_settings.app.get("port", 8080))
    _log.info("starting_server", host=host, port=port, profile=_settings.profile)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
