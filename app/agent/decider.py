"""VERIFY (BAN RUT GON) + DECIDE.

# ASSUMPTION: T09 se xay day du L0-L6 (`app/verify/`) va thay THE ham
`basic_numeric_grounding_check` o day - T08 chi can mot luoi an toan de co
duong tra loi hoan chinh, dung EvidenceSet.matches_any_cell/substitute da co
tu T03. Khong ha thap tieu chuan R1: van CHAN cau tra loi neu con the chua
phan giai duoc, chi la chua co day du 7 lop kiem chung nhu tai lieu 08.
"""

from __future__ import annotations

from app.contracts import Band, CheckResult, Decision, Severity, TrustScore

# Xem docs/09-api-ui.md muc 9.6: "Mau huy hieu: PASS/HEDGE/ABSTAIN/BLOCKED".
_BADGE_LABEL: dict[Band, str] = {
    Band.PASS: "🟢 Đã kiểm chứng",
    Band.HEDGE: "🟡 Cần lưu ý",
    Band.ABSTAIN: "⚪ Không đủ dữ liệu",
    Band.BLOCKED: "🔴 Bị chặn",
}


def basic_numeric_grounding_check(unresolved_tags: list[str]) -> CheckResult:
    """The chua phan giai duoc -> BLOCK ngay (R1: khong bao gio de lot mot
    con so khong co dia chi ra ngoai)."""
    if unresolved_tags:
        return CheckResult(
            name="numeric_grounding_basic", passed=False, score=0.0, severity=Severity.BLOCK,
            details={"unresolved_tags": unresolved_tags},
            message_vi=f"Còn {len(unresolved_tags)} thẻ không phân giải được: {unresolved_tags}",
        )
    return CheckResult(
        name="numeric_grounding_basic", passed=True, score=1.0, severity=Severity.INFO,
    )


def decide(checks: list[CheckResult], t_high: float = 0.85, t_low: float = 0.60) -> TrustScore:
    """Bat ky check BLOCK nao fail -> trust = 0.0 bat ke cac diem khac
    (docs/17-implementation-guide.md T11)."""
    blocking = [c for c in checks if c.severity == Severity.BLOCK and not c.passed]
    if blocking:
        return TrustScore(
            value=0.0, band=Band.BLOCKED, components={c.name: c for c in checks},
            reasons=[c.message_vi or c.name for c in blocking],
        )

    if not checks:
        return TrustScore(value=0.0, band=Band.ABSTAIN, reasons=["khong co check nao chay"])

    avg_score = sum(c.score for c in checks) / len(checks)
    if avg_score >= t_high:
        band = Band.PASS
    elif avg_score >= t_low:
        band = Band.HEDGE
    else:
        band = Band.ABSTAIN

    return TrustScore(value=avg_score, band=band, components={c.name: c for c in checks})


def band_to_decision(band: Band) -> Decision:
    return {
        Band.PASS: Decision.ANSWERED,
        Band.HEDGE: Decision.HEDGED,
        Band.ABSTAIN: Decision.ABSTAINED,
        Band.BLOCKED: Decision.BLOCKED,
    }[band]


def badge_label(band: Band) -> str:
    return _BADGE_LABEL[band]


__all__ = ["basic_numeric_grounding_check", "decide", "band_to_decision", "badge_label"]
