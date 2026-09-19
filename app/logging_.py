"""Cau hinh logging tap trung: structlog, dinh dang JSON o prod, loc bi mat.

Ten file co dau gach duoi ("logging_") de khong dung voi module `logging`
chuan cua Python khi import tuong doi trong `app/`.

QUY TAC (CLAUDE.md): "Khong bao gio log gia tri bi mat." `RedactSecretsProcessor`
la co che ep dieu do - no thay THE moi gia tri xuat hien trong log ma trung
byte-to-byte voi mot bi mat da nap tu Settings, bat ke field nao chua no.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.settings import Settings

_REQUEST_ID_KEY = "trace_id"


def _collect_secret_values(settings: Settings) -> frozenset[str]:
    """Liet ke moi gia tri bi mat da nap, de che trong log.

    Duyet toan bo cay cau hinh da giai quyet (`settings.raw`) va gom nhung
    chuoi nam duoi cac khoa nhay cam thuong gap: api_key, password, secret,
    token, hoac bat ky URL ket noi CSDL (luon chua mat khau).
    """
    sensitive_key_markers = ("key", "secret", "token", "password", "url")
    found: set[str] = set()

    def _walk(node: Any, key_hint: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                _walk(value, key.lower())
        elif isinstance(node, str) and node and any(
            marker in key_hint for marker in sensitive_key_markers
        ):
            found.add(node)

    _walk(settings.raw)
    return frozenset(found)


class RedactSecretsProcessor:
    """Processor cua structlog: thay moi chuoi bi mat da biet bang "***"."""

    def __init__(self, secrets: frozenset[str]) -> None:
        # Bo qua chuoi qua ngan (< 4 ky tu) de khong che nham gia tri thuong
        # nhu port "8080" hay ma trang thai "ok".
        self._secrets = frozenset(s for s in secrets if len(s) >= 4)

    def __call__(
        self, logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        if not self._secrets:
            return event_dict
        for key, value in list(event_dict.items()):
            event_dict[key] = self._redact(value)
        return event_dict

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            redacted = value
            for secret in self._secrets:
                if secret in redacted:
                    redacted = redacted.replace(secret, "***")
            return redacted
        if isinstance(value, dict):
            return {k: self._redact(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self._redact(v) for v in value]
        return value


def configure_logging(settings: Settings) -> None:
    """Goi mot lan luc khoi dong ung dung (main.py). Idempotent."""
    level_name = settings.logging.get("level", "INFO")
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    fmt = settings.logging.get("format", "json")
    secrets = _collect_secret_values(settings) if settings.logging.get(
        "redact_secrets", True
    ) else frozenset()

    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level, force=True
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        RedactSecretsProcessor(secrets),
    ]

    renderer: Any
    if fmt == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Logger da bind san. Goi `configure_logging()` truoc o main.py; neu
    chua goi, structlog dung cau hinh mac dinh (van chay duoc, chi khong loc
    bi mat va khong theo dinh dang du an) - huu ich cho script/test doc lap."""
    return structlog.get_logger(name)


def bind_trace_id(trace_id: str) -> None:
    """Gan `trace_id` vao moi dong log phat ra trong luong hien tai (context-
    var), de moi cau hoi cua nguoi dung truy vet duoc xuyen suot cac module."""
    structlog.contextvars.bind_contextvars(**{_REQUEST_ID_KEY: trace_id})


def clear_trace_id() -> None:
    structlog.contextvars.clear_contextvars()


__all__ = ["configure_logging", "get_logger", "bind_trace_id", "clear_trace_id"]
