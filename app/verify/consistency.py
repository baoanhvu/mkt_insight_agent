"""Self-consistency (chi ap dung duong freeform SQL, T12 - xem
config/verify.yaml khoi `consistency`): sinh k cau tra loi cho CUNG mot cau
hoi (temperature cao hon), gom cum theo "dau van tay" con so, va do ty trong
cum lon nhat. Neu k lan hoi khac nhau ra k con so khac nhau, do la dau hieu
model dang doan chu khong doc du lieu.

THUAN - khong I/O, khong goi LLM (viec goi k lan la cua noi khac, module nay
chi nhan DANH SACH k cau tra loi da co san va tinh toan tren do).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.verify.vi_text import find_bare_numbers, parse_vi_number


def _fingerprint(answer: str, unit_aliases: dict[str, float] | None = None) -> str:
    """Chuoi 'dau van tay' cua mot cau tra loi: danh sach so vi-VN xuat hien
    THEO THU TU, lam tron 4 chu so thap phan de dung sai khac hien thi nho
    (vi du lam tron VND) khong bi coi la hai cau tra loi khac nhau."""
    numbers = (
        parse_vi_number(raw, unit_aliases)
        for raw in find_bare_numbers(answer, tuple((unit_aliases or {}).keys()))
    )
    return "|".join(f"{n:.4f}" for n in numbers if n is not None)


@dataclass(frozen=True, slots=True)
class ConsistencyResult:
    top_cluster_share: float
    n_samples: int
    n_clusters: int
    clusters: dict[str, int] = field(default_factory=dict)


def compute_self_consistency(
    answers: list[str], unit_aliases: dict[str, float] | None = None,
) -> ConsistencyResult:
    """`answers`: k cau tra loi da sinh cho CUNG mot cau hoi (k mau doc lap,
    thuong o temperature cao hon nhu trong config/verify.yaml). Tra ve ty
    trong cum lon nhat - duoi `min_top_cluster_share` (config/verify.yaml)
    la tin hieu ABSTAIN thay vi tra loi."""
    if not answers:
        return ConsistencyResult(top_cluster_share=0.0, n_samples=0, n_clusters=0)

    counts: dict[str, int] = {}
    for answer in answers:
        key = _fingerprint(answer, unit_aliases)
        counts[key] = counts.get(key, 0) + 1

    top = max(counts.values())
    return ConsistencyResult(
        top_cluster_share=top / len(answers), n_samples=len(answers),
        n_clusters=len(counts), clusters=counts,
    )


__all__ = ["ConsistencyResult", "compute_self_consistency"]
