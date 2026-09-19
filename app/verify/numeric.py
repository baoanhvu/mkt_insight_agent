"""L2 - Numeric grounding. LOP QUAN TRONG NHAT (CLAUDE.md R1). Xem
docs/08-anti-hallucination.md muc 8.3.

Thuat toan (khac mot diem nho so voi pseudocode goc trong docs/08, theo huong
DON GIAN HON MA VAN DUNG KET QUA YEU CAU): `parse_vi_number` da tu quy doi
"48,8%" -> 0.488 NGAY LUC PHAN TICH CHUOI (chia 100 khi co hau to '%'), nen
khi so sanh voi Cell (da luu duoi dang ty le 0..1) khong can co che "alias
ratio_x100" rieng o buoc khop - phep chia da xay ra truoc do.
"""

from __future__ import annotations

from typing import Literal, cast

from app.contracts import CheckResult, NumericPolicy, Severity
from app.semantic.evidence import EvidenceSet
from app.verify.config import VerifyConfig, get_verify_config
from app.verify.vi_text import extract_evidence_refs, find_bare_numbers, parse_vi_number


def _is_allowlisted(value: float, cfg: VerifyConfig) -> bool:
    if value in cfg.allowlist_literals:
        return True
    lo, hi = cfg.allowlist_years
    if lo <= value <= hi and float(value).is_integer():
        return True
    lo2, hi2 = cfg.allowlist_ordinals
    return lo2 <= value <= hi2 and float(value).is_integer()


def _to_numeric_policy(cfg: VerifyConfig, policy_name: str) -> NumericPolicy:
    spec = cfg.numeric_policies[policy_name]
    mode = cast(Literal["exact", "round", "rel_tol", "abs_tol"], spec.mode)
    return NumericPolicy(mode=mode, decimals=spec.decimals, tol=spec.tol, aliases=spec.alias)


def _matches_under_any_policy(value: float, ev: EvidenceSet, cfg: VerifyConfig) -> bool:
    """Thu khop voi TAT CA chinh sach da khai bao (default/vnd/ratio/percent/...)
    truoc khi ket luan mot so la "bia" - mot so tran co the la VND, co the la
    ty le, ta khong biet truoc no thuoc chinh sach nao."""
    for name in cfg.numeric_policies:
        if ev.matches_any_cell(value, _to_numeric_policy(cfg, name)):
            return True
    return False


def check_numeric_grounding(
    text: str, ev: EvidenceSet, cfg: VerifyConfig | None = None,
) -> CheckResult:
    """text la van ban DA duoc ev.substitute() (tuc da thay {{...}} -> so that)
    HOAC van con the - ham nay tu goi substitute() lai mot lan de lay chuoi
    hien thi cuoi cung dung cho buoc quet so tran, va tu kiem tra tag truoc do
    tren van ban GOC (truoc thay the) de biet tag nao khong phan giai duoc."""
    cfg = cfg or get_verify_config()

    refs = extract_evidence_refs(text)
    unresolved_tags = [ref for ref in refs if ev.resolve(ref) is None]

    rendered_text, _ = ev.substitute(text)

    bare_numbers: list[str] = []
    for raw in find_bare_numbers(rendered_text, tuple(cfg.unit_aliases)):
        value = parse_vi_number(raw, cfg.unit_aliases)
        if value is None:
            continue
        if _is_allowlisted(value, cfg):
            continue
        if _matches_under_any_policy(value, ev, cfg):
            continue  # so dung nhung viet thang - se duoc canh bao o buoc khac, KHONG chan o day
        bare_numbers.append(raw)

    resolved_count = len(refs) - len(unresolved_tags)
    total = resolved_count + len(unresolved_tags) + len(bare_numbers)
    rate = resolved_count / total if total else 1.0

    passed = not unresolved_tags and not bare_numbers
    details = {
        "resolved": resolved_count, "unresolved_tags": unresolved_tags,
        "ungrounded_numbers": bare_numbers,
    }
    message_vi = None
    if not passed:
        message_vi = (
            f"Còn {len(unresolved_tags)} thẻ không phân giải được và "
            f"{len(bare_numbers)} số viết thẳng không khớp dữ liệu."
        )

    return CheckResult(
        name="numeric_grounding", passed=passed, score=rate, severity=Severity.BLOCK,
        details=details, message_vi=message_vi,
    )


__all__ = ["check_numeric_grounding"]
