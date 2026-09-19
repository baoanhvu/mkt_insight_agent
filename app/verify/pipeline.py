"""Chay L2 (numeric) + L3 (entity) + L4 (stats guard), tong hop thanh
TrustScore. Xem docs/08-anti-hallucination.md muc 8.7 (L6).

L0/L1 (SQL tinh - chi duong freeform) la T12. L5 (LLM judge, bat dong bo) la
T11 - `compute_trust` da chua san mot khoa "judge" trong hard-fail check theo
dung docs, chi don gian bo qua neu chua co ket qua judge (chua chay xong).
"""

from __future__ import annotations

from app.contracts import Band, CheckResult, Decision, TrustScore
from app.semantic.catalog import YamlCatalog
from app.semantic.evidence import EvidenceSet
from app.verify.config import VerifyConfig, get_verify_config
from app.verify.entity import check_entity_grounding
from app.verify.numeric import check_numeric_grounding
from app.verify.stats_guard import check_stats_guard

_SHORT_NAMES: dict[str, str] = {
    "numeric_grounding": "numeric", "entity_grounding": "entity", "stats_guard": "stats",
    "judge": "judge", "sql_validation": "schema", "consistency": "consistency",
}


def run_deterministic_checks(
    text: str, ev: EvidenceSet, catalog: YamlCatalog, cfg: VerifyConfig | None = None,
) -> list[CheckResult]:
    """L2 + L3 + L4 - tat dinh, khong I/O, khong goi LLM (~10ms tong cong)."""
    cfg = cfg or get_verify_config()
    return [
        check_numeric_grounding(text, ev, cfg),
        check_entity_grounding(text, ev, catalog, cfg),
        check_stats_guard(text, ev, cfg),
    ]


def compute_trust(checks: list[CheckResult], cfg: VerifyConfig | None = None) -> TrustScore:
    """KHONG lay trung binh cong cac diem khac ban chat (docs/08 muc 8.7).
    Tap hard-fail duoc kiem TRUOC; bat ky muc BLOCK nao fail -> trust = 0,0
    bat ke diem cac muc khac."""
    cfg = cfg or get_verify_config()
    by_name = {c.name: c for c in checks}

    hard_fail = [c for c in checks if c.severity == "BLOCK" and not c.passed]
    if hard_fail:
        return TrustScore(
            value=0.0, band=Band.BLOCKED, components=by_name,
            reasons=[c.message_vi or c.name for c in hard_fail],
        )

    if not checks:
        return TrustScore(value=0.0, band=Band.ABSTAIN, reasons=["khong co check nao chay"])

    weights = cfg.trust_weights
    weighted_sum = 0.0
    weight_total = 0.0
    for c in checks:
        w = weights.get(_SHORT_NAMES.get(c.name, c.name), 0.0)
        weighted_sum += c.score * w
        weight_total += w
    value = weighted_sum / weight_total if weight_total else sum(c.score for c in checks) / len(checks)

    if value >= cfg.t_high:
        band = Band.PASS
    elif value >= cfg.t_low:
        band = Band.HEDGE
    else:
        band = Band.ABSTAIN

    return TrustScore(value=value, band=band, components=by_name)


def band_to_decision(band: Band) -> Decision:
    return {
        Band.PASS: Decision.ANSWERED,
        Band.HEDGE: Decision.HEDGED,
        Band.ABSTAIN: Decision.ABSTAINED,
        Band.BLOCKED: Decision.BLOCKED,
    }[band]


# Xem docs/09-api-ui.md muc 9.6: "Mau huy hieu: PASS/HEDGE/ABSTAIN/BLOCKED".
_BADGE_LABEL: dict[Band, str] = {
    Band.PASS: "🟢 Đã kiểm chứng",
    Band.HEDGE: "🟡 Cần lưu ý",
    Band.ABSTAIN: "⚪ Không đủ dữ liệu",
    Band.BLOCKED: "🔴 Bị chặn",
}


def badge_label(band: Band) -> str:
    return _BADGE_LABEL[band]


__all__ = ["run_deterministic_checks", "compute_trust", "band_to_decision", "badge_label"]
