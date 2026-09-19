"""`OpenAICompatibleClient` - boc `openai.AsyncOpenAI` tro vao base_url cua
MaaS (hoac Ollama o profile local). Trien khai `app.contracts.LLMClient`.

- Token bucket phia CLIENT (mac dinh 8 req/phut) - KHONG dua vao bat loi 429.
- Retry co backoff mu cho 408/429/500/502/503/504, toi da `max_retries`.
- Ghi usage (token vao/ra) vao `UsageCounters` truyen tu ngoai.
- Het luot thu -> raise `LLMUnavailable`/`LLMRateLimited`/`LLMTimeout` de
  orchestrator (T08) chuyen sang che do template.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from app.errors import LLMRateLimited, LLMTimeout, LLMUnavailable
from app.llm.usage import UsageCounters
from app.logging_ import get_logger

log = get_logger(__name__)

_DEFAULT_RETRY_STATUS = (408, 429, 500, 502, 503, 504)


class _TokenBucket:
    """Token bucket async don gian, tong quat hoa theo (rate_per_window,
    window_seconds) de test duoc nhanh ma khong can doi ca phut thuc."""

    def __init__(self, rate_per_window: float, window_seconds: float, burst: float) -> None:
        if rate_per_window <= 0 or window_seconds <= 0:
            raise ValueError("rate_per_window va window_seconds phai > 0")
        self._rate_per_second = rate_per_window / window_seconds
        self._capacity = max(burst, 1.0)
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_second)
                self._updated_at = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_s = (1.0 - self._tokens) / self._rate_per_second
            await asyncio.sleep(wait_s)


class OpenAICompatibleClient:
    """Trien khai `app.contracts.LLMClient`."""

    def __init__(
        self, *, base_url: str, api_key: str, model: str,
        timeout_s: float = 60.0, max_retries: int = 3,
        retry_backoff_base_s: float = 2.0,
        retry_on_status: tuple[int, ...] = _DEFAULT_RETRY_STATUS,
        requests_per_minute: float = 8.0, burst: float = 3.0,
        usage: UsageCounters | None = None,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s)
        self.model = model
        self.max_retries = max_retries
        self.retry_backoff_base_s = retry_backoff_base_s
        self.retry_on_status = retry_on_status
        self._bucket = _TokenBucket(requests_per_minute, 60.0, burst)
        self.usage = usage if usage is not None else UsageCounters()

    def _build_kwargs(
        self, messages: list[dict[str, str]], model: str | None, temperature: float | None,
        max_tokens: int | None, response_format: Literal["text", "json"], stream: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": model or self.model, "messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        if stream:
            kwargs["stream"] = True
        return kwargs

    async def complete(
        self, messages: list[dict[str, str]], *,
        model: str | None = None, temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: Literal["text", "json"] = "text",
    ) -> str:
        await self._bucket.acquire()
        kwargs = self._build_kwargs(messages, model, temperature, max_tokens, response_format, False)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except APIStatusError as exc:
                last_exc = exc
                if exc.status_code == 429 and attempt >= self.max_retries:
                    raise LLMRateLimited(str(exc), status_code=exc.status_code) from exc
                if exc.status_code not in self.retry_on_status or attempt >= self.max_retries:
                    raise LLMUnavailable(str(exc), status_code=exc.status_code) from exc
            except APITimeoutError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise LLMTimeout(str(exc)) from exc
            except APIConnectionError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise LLMUnavailable(str(exc)) from exc
            else:
                content = resp.choices[0].message.content or ""
                usage = getattr(resp, "usage", None)
                self.usage.add(
                    tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
                    tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
                )
                return content

            backoff = self.retry_backoff_base_s * (2**attempt) + random.uniform(0, 0.5)
            log.warning("llm_retry", attempt=attempt, backoff_s=round(backoff, 2),
                        error=str(last_exc))
            await asyncio.sleep(backoff)

        raise LLMUnavailable(f"het luot thu ({self.max_retries}): {last_exc}")

    async def stream(self, messages: list[dict[str, str]], **kwargs: Any) -> AsyncIterator[str]:
        await self._bucket.acquire()
        params = self._build_kwargs(
            messages, kwargs.get("model"), kwargs.get("temperature"),
            kwargs.get("max_tokens"), kwargs.get("response_format", "text"), True,
        )
        try:
            response_stream = await self._client.chat.completions.create(**params)
            async for chunk in response_stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except (APIStatusError, APITimeoutError, APIConnectionError) as exc:
            raise LLMUnavailable(str(exc)) from exc


__all__ = ["OpenAICompatibleClient"]
