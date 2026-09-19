"""RENDER: thay the {{F1.r1.romi}} -> so that, da dinh dang vi-VN (Cell.formatted
tu T03). Xem docs/05-semantic-layer.md muc 5.4 va docs/09-api-ui.md muc 9.8.
"""

from __future__ import annotations

from app.semantic.evidence import EvidenceSet


def render_narrative(narrative_template: str, ev: EvidenceSet) -> tuple[str, list[str]]:
    """Tra ve (van_ban_da_thay_the, danh_sach_the_khong_phan_giai_duoc)."""
    return ev.substitute(narrative_template)


__all__ = ["render_narrative"]
