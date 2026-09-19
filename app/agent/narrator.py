"""NARRATE: EvidenceSet -> van ban co THE, khong co chu so (1 goi LLM).
Trien khai `app.contracts.Narrator`. Xem docs/05-semantic-layer.md muc 5.4
(cach dia chi hoa) va docs/07-prompt-fewshot.md (cau truc prompt).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agent.playbooks import PlaybookStore
from app.contracts import LLMClient
from app.prompts.loader import PromptLoader
from app.semantic.evidence import EvidenceSet


def serialize_evidence(ev: EvidenceSet) -> str:
    """Chuoi hoa EvidenceSet dung DANG few-shot trong prompts/narrate_*.yaml
    (vi du "F1.r1.romi = 6.20") - de LLM thay dung dinh dang no da hoc."""
    lines: list[str] = []
    for fact in ev.facts:
        lines.append(f"# {fact.fact_id}: {fact.title} (n={fact.row_count})")
        if fact.caveats:
            lines.append(f"  caveats: {'; '.join(fact.caveats)}")
        for row in fact.rows:
            ref = row.get("_ref", fact.fact_id)
            parts = [f"{ref}.{k} = {v!r}" for k, v in row.items() if k != "_ref"]
            lines.append("   " + "   ".join(parts))
    for d in ev.derived:
        lines.append(f"# {d.fact_id} ({d.label_vi}): {d.fact_id} = {d.value!r}  [{d.expr}]")
    for i, comp in enumerate(ev.comparisons, start=1):
        lines.append(
            f"# C{i}: so sanh {comp.left} vs {comp.right} ({comp.metric}) - "
            f"diff={comp.diff!r}, p_value={comp.p_value!r}, significant={comp.significant}"
        )
    if ev.caveats:
        lines.append("caveats(chung): " + "; ".join(ev.caveats))
    if ev.assumptions:
        lines.append("assumptions: " + "; ".join(ev.assumptions))
    if ev.actions:
        lines.append(f"actions: {ev.actions}")
    return "\n".join(lines)


class LLMNarrator:
    def __init__(
        self, prompts: PromptLoader, llm_client: LLMClient, playbook_store: PlaybookStore,
    ) -> None:
        self.prompts = prompts
        self.llm_client = llm_client
        self.playbook_store = playbook_store

    def _build_messages(
        self, playbook_id: str, ev: EvidenceSet, question: str,
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        playbook = self.playbook_store.get(playbook_id)
        rendered = self.prompts.render(
            playbook.prompt,
            tone="trực tiếp, không hoa mỹ",
            max_words=playbook.max_words or 400,
            sections=[{"label_vi": s.label_vi} for s in playbook.sections],
        )
        messages = list(rendered.messages)
        messages.append({
            "role": "user",
            "content": f"EVIDENCE:\n{serialize_evidence(ev)}\n\nCÂU HỎI: {question}",
        })
        return messages, rendered.params

    async def narrate(self, playbook_id: str, ev: EvidenceSet, question: str) -> str:
        messages, params = self._build_messages(playbook_id, ev, question)
        return await self.llm_client.complete(
            messages, temperature=params.get("temperature", 0.2),
            max_tokens=params.get("max_tokens", 1200),
        )

    async def narrate_stream(
        self, playbook_id: str, ev: EvidenceSet, question: str,
    ) -> AsyncIterator[str]:
        # Ban day du se hoan thien o T10 (StreamingVerifier). Tam thoi goi
        # non-stream roi phat mot khoi duy nhat, giu dung hop dong Protocol.
        text = await self.narrate(playbook_id, ev, question)
        yield text


__all__ = ["LLMNarrator", "serialize_evidence"]
