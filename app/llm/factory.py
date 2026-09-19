"""Chon provider LLM theo `settings.llm.provider` - "mock" (profile test) hoac
"openai_compatible" (local/greennode). Diem lap rap DUY NHAT; agent (T08)
khong tu quyet dinh provider.
"""

from __future__ import annotations

from pathlib import Path

from app.contracts import LLMClient
from app.errors import MissingSecretError
from app.llm.client import OpenAICompatibleClient
from app.llm.mock import MockLLMClient
from app.llm.usage import UsageCounters
from app.settings import Settings

ROOT = Path(__file__).resolve().parent.parent.parent


def build_llm_client(settings: Settings, usage: UsageCounters | None = None) -> LLMClient:
    provider = str(settings.llm.get("provider", "openai_compatible"))

    if provider == "mock":
        response_dir_raw = settings.llm.get("mock_response_dir")
        response_dir = (ROOT / response_dir_raw) if response_dir_raw else None
        # app.contracts.LLMClient.stream duoc khai bao "async def ... -> AsyncIterator[str]"
        # (than la "..."). mypy doc dang do la mot coroutine TRA VE AsyncIterator,
        # trong khi ca hai lop o day trien khai `stream` nhu mot async generator
        # THAT (co yield) - ban chat khac voi coroutine du cung mo ta bang
        # AsyncIterator[str]. Day la mot dac thu cua chinh contracts.py (protected,
        # khong sua duoc); hai lop van khop dung ve mat hanh vi (dung duoc qua
        # `async for` nhu moi noi khac trong du an).
        return MockLLMClient(response_dir=response_dir)  # type: ignore[return-value]

    base_url = settings.llm.get("base_url") or settings.llm.get("base_url_default")
    api_key = settings.llm.get("api_key")
    model = settings.llm.get("model") or settings.llm.get("model_fallback")
    if not base_url or not api_key or not model:
        raise MissingSecretError(
            "thieu llm.base_url/api_key/model - kiem tra config/profiles va "
            "config/secrets.yaml (xem docs/10-config-secrets.md)"
        )

    # `settings.llm.get(...)` boc ket qua dict thanh ConfigNode (xem
    # app/settings.py) - chuoi .get() lien tiep o day dua vao chinh co che do,
    # KHONG dung isinstance(..., dict) vi ket qua se luon la ConfigNode.
    rate_limit = settings.llm.get("rate_limit", {})
    return OpenAICompatibleClient(  # type: ignore[return-value]  # xem ghi chu o nhanh "mock" tren
        base_url=str(base_url), api_key=str(api_key), model=str(model),
        timeout_s=float(settings.llm.get("timeout_s", 60.0)),
        max_retries=int(settings.llm.get("max_retries", 3)),
        retry_backoff_base_s=float(settings.llm.get("retry_backoff_base_s", 2.0)),
        retry_on_status=tuple(settings.llm.get("retry_on_status", (408, 429, 500, 502, 503, 504))),
        requests_per_minute=float(rate_limit.get("requests_per_minute", 8)),
        burst=float(rate_limit.get("burst", 3)),
        usage=usage,
    )


__all__ = ["build_llm_client"]
