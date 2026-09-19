"""Dem token va so luot goi LLM. Ket qua di thang vao `AgentState`
(llm_calls/tokens_in/tokens_out) roi vao `ops.agent_trace` - xem
docs/08-anti-hallucination.md ve ngan sach toi da 2 luot goi LLM/cau hoi.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UsageCounters:
    """Bo dem CHIA SE giua cac lan goi trong CUNG mot cau hoi. Mot instance
    moi cho moi `AgentState` - khong dung chung giua nhieu cau hoi."""

    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def add(self, tokens_in: int, tokens_out: int) -> None:
        self.llm_calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def reset(self) -> None:
        self.llm_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0


def estimate_tokens_vi(text: str) -> int:
    """Uoc luong THO so token cho van ban tieng Viet co dau, dung khi provider
    (vi du mock) khong tra ve `usage` thuc. KHONG dung ket qua nay de tinh
    tien hay de quyet dinh nghiep vu - chi la con so tham khao cho log/test.

    Tieng Viet co dau thuong tach thanh nhieu token hon tieng Anh cho cung so
    ky tu (dau thanh + dau mu la cac ky tu Unicode rieng voi hau het BPE
    tokenizer) - he so 1/3 ky tu/token (thay vi 1/4 nhu tieng Anh) phan anh
    dieu do, nhung day van chi la xap xi."""
    if not text:
        return 0
    return max(1, len(text) // 3)


__all__ = ["UsageCounters", "estimate_tokens_vi"]
