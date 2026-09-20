"""Bo dem streaming co kiem chung (L2 + L3 tren TUNG KHOI). Xem
docs/15-streaming.md muc 15.4.

Gom token LLM thanh khoi markdown hoan chinh (mot doan van, mot tieu de, mot
gach dau dong), thay the the {{...}}, chay L2 (numeric) + L3 (entity) TREN
CHINH khoi do, roi moi phat ra ngoai. Khong bao gio de mot the {{...}} chua
phan giai hoac mot so tran chua kiem chung lot len man hinh - client chi
nhan `AgentEvent(event="block")` voi `md` la None khi khoi khong dat, KHONG
BAO GIO hien noi dung roi rut lai sau.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.contracts import AgentEvent, VerifiedBlock
from app.semantic.catalog import YamlCatalog
from app.semantic.evidence import EvidenceSet
from app.verify.entity import check_entity_grounding
from app.verify.numeric import check_numeric_grounding

# Ranh gioi "an toan" de cat mot khoi markdown - cuoi doan/tieu de/gach dau
# dong. Sap xep dai truoc de tranh cat nham mot ranh gioi ngan hon nam trong
# mot ranh gioi dai hon tai cung vi tri.
FLUSH_ON: tuple[str, ...] = ("\n\n", "\n### ", "\n## ", "\n- ", "\n* ", "\n1. ")


class StreamingVerifier:
    """Nhan token tu `Narrator.narrate_stream`, phat ra `AgentEvent(event="block")`
    khi mot khoi markdown hoan chinh da duoc kiem chung."""

    def __init__(
        self, evidence: EvidenceSet, catalog: YamlCatalog, max_block_chars: int = 600,
    ) -> None:
        self.evidence = evidence
        self.catalog = catalog
        self.max_block_chars = max_block_chars
        self._buf: str = ""
        self._seq: int = 0
        self.blocks: list[VerifiedBlock] = []

    def feed(self, token: str) -> Iterator[AgentEvent]:
        """Nap mot token (hoac mot doan token). Sinh ra 0..n su kien `block`."""
        self._buf += token
        while (cut := self._find_safe_cut()) is not None:
            piece = self._buf[:cut]
            self._buf = self._buf[cut:]
            yield self._emit(piece)

    def finish(self) -> Iterator[AgentEvent]:
        """Goi khi LLM stream xong - day not phan con lai trong buffer."""
        if self._buf.strip():
            yield self._emit(self._buf)
        self._buf = ""

    @property
    def full_raw_text(self) -> str:
        """Ghep lai TOAN BO van ban goc (con the) da tung di qua bo dem nay -
        dung de chay lai VERIFY day du (L2+L3+L4) tren toan bo cau tra loi,
        giong het duong khong-streaming (`Orchestrator.answer`)."""
        return "".join(b.raw for b in self.blocks)

    # ---- noi bo ------------------------------------------------------

    def _has_open_tag(self) -> bool:
        """The dang mo do la '{{' xuat hien SAU '}}' gan nhat (hoac chua co
        '}}' nao ca) - tuc con mot the chua dong trong buffer."""
        return self._buf.rfind("{{") > self._buf.rfind("}}")

    def _find_safe_cut(self) -> int | None:
        """Vi tri cat an toan, hoac None neu chua the cat. KHONG BAO GIO cat
        vao giua mot the {{...}} dang viet do - neu buffer co the mo dang do,
        chi tim ranh gioi trong PHAN TRUOC the do, de doan van phia truoc van
        chay ra binh thuong ngay ca khi the phia sau chua viet xong."""
        region = self._buf[: self._buf.rfind("{{")] if self._has_open_tag() else self._buf

        best = max((region.rfind(marker) for marker in FLUSH_ON), default=-1)
        if best >= 0:
            return best + 1

        if len(region) > self.max_block_chars:
            space_at = region.rfind(" ", 0, self.max_block_chars)
            return space_at if space_at > 0 else None
        return None

    def _emit(self, raw: str) -> AgentEvent:
        md, unresolved = self.evidence.substitute(raw)
        numeric = check_numeric_grounding(md, self.evidence)
        entity = check_entity_grounding(md, self.evidence, self.catalog)
        ok = not unresolved and numeric.passed and entity.passed

        self._seq += 1
        block = VerifiedBlock(
            seq=self._seq, raw=raw, md=md if ok else None, verified=ok,
            numeric=numeric, entity=entity, unresolved_tags=unresolved,
        )
        self.blocks.append(block)

        data: dict[str, object] = {"seq": block.seq, "md": block.md, "verified": block.verified}
        if ok:
            total = (
                numeric.details.get("resolved", 0)
                + len(numeric.details.get("unresolved_tags", ()))
                + len(numeric.details.get("ungrounded_numbers", ()))
            )
            data["numbers"] = {"ok": numeric.details.get("resolved", 0), "total": total}
        else:
            reason = (
                "unresolved_tag" if unresolved
                else "numeric_ungrounded" if not numeric.passed
                else "entity_ungrounded"
            )
            data["reason"] = reason
            data["detail"] = (
                unresolved or numeric.details.get("ungrounded_numbers")
                or entity.details.get("unknown_entities") or []
            )
        return AgentEvent(event="block", data=data)


__all__ = ["StreamingVerifier", "FLUSH_ON"]
