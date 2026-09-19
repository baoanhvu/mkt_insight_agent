"""Kiem tra app/llm/{client,mock,usage}.py.

BAT BUOC (docs/17-implementation-guide.md T07):
  - rate limit: 20 request dong thoi -> khong request nao vuot 8/phut
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.errors import LLMRateLimited, LLMTimeout, LLMUnavailable
from app.llm.client import OpenAICompatibleClient, _TokenBucket
from app.llm.mock import MockLLMClient
from app.llm.usage import UsageCounters, estimate_tokens_vi


def _fake_status_error(status_code: int) -> APIStatusError:
    resp = httpx.Response(status_code=status_code, request=httpx.Request("POST", "http://x"))
    return APIStatusError(f"loi {status_code}", response=resp, body=None)


def _fake_completion(content: str = "ok", tokens_in: int = 10, tokens_out: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out),
    )


def _fast_client(**overrides: object) -> OpenAICompatibleClient:
    """Client voi rate limit rong (khong can doi) - danh cho test logic
    retry/mapping loi, khong phai test rate limit."""
    kwargs = {
        "base_url": "http://localhost:1", "api_key": "test", "model": "mock-model",
        "max_retries": 2, "retry_backoff_base_s": 0.01,
        "requests_per_minute": 100_000, "burst": 100_000,
    }
    kwargs.update(overrides)
    return OpenAICompatibleClient(**kwargs)  # type: ignore[arg-type]


# =============================================================================
# _TokenBucket - BAT BUOC: gioi han toc do thuc su co hieu luc
# =============================================================================

async def test_token_bucket_caps_throughput_below_configured_rate() -> None:
    """20 request dong thoi voi rate=8/phut, burst=3 - trong 2 giay dau tien
    KHONG duoc vuot qua burst + mot phan nho cua rate (~8/60*2 ~ 0.27), tuc
    toi da burst + 1. Dung thang thoi gian rut gon (rate/window nho) de test
    nhanh thay vi phai doi ca phut thuc - thuat toan la tuyen tinh theo ty le
    rate/window nen ket qua tuong duong."""
    bucket = _TokenBucket(rate_per_window=8, window_seconds=60.0, burst=3)
    completed_at: list[float] = []
    start = time.monotonic()

    async def _one() -> None:
        await bucket.acquire()
        completed_at.append(time.monotonic() - start)

    tasks = [asyncio.create_task(_one()) for _ in range(20)]
    # Doi toi da 2 giay thuc - chi du de burst (3) + mot vai token nho tiep
    # tuc duoc cap, KHONG du de 20 request deu hoan thanh (~142s neu dung 8/phut).
    done, pending = await asyncio.wait(tasks, timeout=2.0)
    for t in pending:
        t.cancel()

    assert len(done) <= 5, f"{len(done)} request hoan thanh trong 2s - rate limit khong co hieu luc"
    assert len(done) >= 3, "it nhat 'burst' request phai hoan thanh ngay"


async def test_token_bucket_refills_over_time() -> None:
    """Rate/window duoc rut gon (8 token / 2 giay = 4 token/giay) de test
    nhanh: sau khi can burst, token phai duoc cap lai theo dung ty le thoi
    gian troi qua, khong dung han lai vinh vien."""
    bucket = _TokenBucket(rate_per_window=8, window_seconds=2.0, burst=2)
    await bucket.acquire()
    await bucket.acquire()  # can het burst=2

    start = time.monotonic()
    await bucket.acquire()  # phai doi toi khi co token moi
    elapsed = time.monotonic() - start
    assert elapsed > 0.1, "khong doi gi ca - rate limit khong hoat dong"
    assert elapsed < 1.0, "doi qua lau so voi rate da cau hinh"


def test_token_bucket_rejects_invalid_config() -> None:
    with pytest.raises(ValueError):
        _TokenBucket(rate_per_window=0, window_seconds=60, burst=3)
    with pytest.raises(ValueError):
        _TokenBucket(rate_per_window=8, window_seconds=0, burst=3)


# =============================================================================
# MockLLMClient - 0 loi goi mang, dung cho profile test
# =============================================================================

async def test_mock_client_returns_default_when_no_fixture() -> None:
    client = MockLLMClient(response_dir=None)
    text = await client.complete([{"role": "user", "content": "cau hoi bat ky"}])
    assert text
    assert len(client.calls) == 1


async def test_mock_client_returns_json_default_for_json_format() -> None:
    client = MockLLMClient()
    text = await client.complete(
        [{"role": "user", "content": "phan loai"}], response_format="json"
    )
    import json

    parsed = json.loads(text)  # phai la JSON hop le
    assert "intent" in parsed


async def test_mock_client_reads_fixture_file(tmp_path: Path) -> None:
    from app.llm.mock import _fixture_key

    messages = [{"role": "user", "content": "cau hoi co fixture"}]
    key = _fixture_key(messages)
    (tmp_path / f"{key}.txt").write_text("cau tra loi mau tu fixture", encoding="utf-8")

    client = MockLLMClient(response_dir=tmp_path)
    text = await client.complete(messages)
    assert text == "cau tra loi mau tu fixture"


async def test_mock_client_stream_yields_chunks_that_join_to_full_text() -> None:
    client = MockLLMClient()
    messages = [{"role": "user", "content": "test stream"}]
    full = await client.complete(messages)
    client2 = MockLLMClient()
    chunks = [c async for c in client2.stream(messages)]
    assert "".join(chunks) == full


async def test_mock_client_tracks_usage() -> None:
    client = MockLLMClient()
    await client.complete([{"role": "user", "content": "abc"}])
    assert client.usage.llm_calls == 1
    assert client.usage.tokens_in > 0
    assert client.usage.tokens_out > 0


# =============================================================================
# UsageCounters
# =============================================================================

def test_usage_counters_accumulate() -> None:
    u = UsageCounters()
    u.add(tokens_in=10, tokens_out=20)
    u.add(tokens_in=5, tokens_out=8)
    assert u.llm_calls == 2
    assert u.tokens_in == 15
    assert u.tokens_out == 28
    u.reset()
    assert u.llm_calls == 0


def test_estimate_tokens_vi_nonzero_for_nonempty_text() -> None:
    assert estimate_tokens_vi("") == 0
    assert estimate_tokens_vi("Chiến dịch nào đang lỗ?") > 0


# =============================================================================
# OpenAICompatibleClient - retry, mapping loi, usage
# =============================================================================

async def test_complete_returns_content_and_tracks_usage() -> None:
    client = _fast_client()
    client._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_fake_completion("xin chao", tokens_in=12, tokens_out=7)
    )
    text = await client.complete([{"role": "user", "content": "hi"}])
    assert text == "xin chao"
    assert client.usage.llm_calls == 1
    assert client.usage.tokens_in == 12
    assert client.usage.tokens_out == 7


async def test_complete_retries_on_retryable_status_then_succeeds() -> None:
    client = _fast_client()
    client._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_fake_status_error(503), _fake_completion("thanh cong lan 2")]
    )
    text = await client.complete([{"role": "user", "content": "hi"}])
    assert text == "thanh cong lan 2"
    assert client._client.chat.completions.create.call_count == 2


async def test_complete_raises_llm_rate_limited_after_exhausting_retries_on_429() -> None:
    client = _fast_client(max_retries=1)
    client._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=_fake_status_error(429)
    )
    with pytest.raises(LLMRateLimited):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_complete_raises_llm_unavailable_on_non_retryable_status() -> None:
    client = _fast_client()
    client._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=_fake_status_error(400)
    )
    with pytest.raises(LLMUnavailable):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_complete_raises_llm_timeout_after_exhausting_retries() -> None:
    client = _fast_client(max_retries=1)
    client._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APITimeoutError(request=httpx.Request("POST", "http://x"))
    )
    with pytest.raises(LLMTimeout):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_complete_raises_llm_unavailable_on_connection_error() -> None:
    client = _fast_client(max_retries=0)
    client._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=APIConnectionError(request=httpx.Request("POST", "http://x"))
    )
    with pytest.raises(LLMUnavailable):
        await client.complete([{"role": "user", "content": "hi"}])
