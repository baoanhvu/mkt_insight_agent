"""Provider "mock" - 0 loi goi mang, dung cho `APP_PROFILE=test` (xem
config/profiles/test.yaml -> llm.provider). Day la thu lam golden set va
toan bo test chay duoc trong CI ma khong ton quota MaaS va khong phu thuoc
mang - dung tran 10 RPM cua tai khoan chung.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Literal

from app.llm.usage import UsageCounters, estimate_tokens_vi

_DEFAULT_JSON = '{"intent": "data_question", "entities": {}, "confidence": 0.5}'
_DEFAULT_TEXT = (
    "### Kết luận\n"
    "Chưa có bằng chứng cụ thể cho câu hỏi này (câu trả lời mẫu từ provider mock)."
)


def _last_user_message(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _fixture_key(messages: list[dict[str, str]]) -> str:
    payload = _last_user_message(messages)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _chunk(text: str, size: int = 16) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


class MockLLMClient:
    """Trien khai `app.contracts.LLMClient`. Doc cau tra loi mau tu
    `response_dir/<sha1_16_ky_tu_cua_tin_nhan_user_cuoi>.txt`; khong thay file
    thi tra mot cau tra loi an toan mac dinh theo `response_format`, de agent
    van chay duoc ngay ca khi chua chuan bi fixture cho tinh huong do.

    `calls` ghi lai toan bo loi goi - test doc lai de kiem tra so luot goi,
    dung thay cho mock/patch cua thu vien ngoai.
    """

    def __init__(self, response_dir: Path | None = None) -> None:
        self.response_dir = response_dir
        self.calls: list[dict[str, Any]] = []
        self.usage = UsageCounters()

    def _lookup_fixture(self, messages: list[dict[str, str]]) -> str | None:
        if self.response_dir is None:
            return None
        candidate = self.response_dir / f"{_fixture_key(messages)}.txt"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
        return None

    async def complete(
        self, messages: list[dict[str, str]], *,
        model: str | None = None, temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: Literal["text", "json"] = "text",
    ) -> str:
        self.calls.append({
            "messages": messages, "model": model, "temperature": temperature,
            "max_tokens": max_tokens, "response_format": response_format,
        })
        fixture = self._lookup_fixture(messages)
        text = fixture if fixture is not None else (
            _DEFAULT_JSON if response_format == "json" else _DEFAULT_TEXT
        )
        self.usage.add(
            tokens_in=estimate_tokens_vi(_last_user_message(messages)),
            tokens_out=estimate_tokens_vi(text),
        )
        return text

    async def stream(self, messages: list[dict[str, str]], **kwargs: Any) -> AsyncIterator[str]:
        text = await self.complete(messages, **kwargs)
        for piece in _chunk(text):
            yield piece


__all__ = ["MockLLMClient"]
