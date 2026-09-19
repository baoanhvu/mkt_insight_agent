"""L4 - Stats guard: lop ma bo du lieu nay BAT BUOC phai co (docs/08-anti-hallucination.md
muc 8.4). Khong lop grounding nao bat duoc "Freelancer sinh lời nhất" - con so
220.200 THAT SU co trong ket qua truy van, chi la chenh lech nam trong nhieu
(ANOVA p=0,9718 tren 7 nhom nghe). Can mot lop rieng doc VAO ket qua kiem dinh
da tinh san trong `EvidenceSet.comparisons`.

# ASSUMPTION: pseudocode goc trong docs/08 tim CAP (left, right) CU THE ma
mot cau dang noi toi. O day don gian hoa: mot cau co marker so sanh duoc coi
la "co can cu" neu EvidenceSet co IT NHAT MOT Comparison significant=True -
chua khop chinh xac cap thuc the duoc nhac trong cau do. Voi cach dung hien
tai (mot playbook thuong chi tinh MOT bo so sanh lien quan cho moi cau hoi),
day la xap xi hop ly; khop chinh xac theo cap la mot cai tien co the lam sau.
"""

from __future__ import annotations

from app.contracts import CheckResult, Severity
from app.semantic.evidence import EvidenceSet
from app.verify.config import VerifyConfig, get_verify_config
from app.verify.vi_text import contains_any_marker, split_sentences_vi


def check_stats_guard(
    text: str, ev: EvidenceSet, cfg: VerifyConfig | None = None,
) -> CheckResult:
    cfg = cfg or get_verify_config()
    rendered_text, _ = ev.substitute(text)
    sentences = split_sentences_vi(rendered_text)

    has_significant_comparison = any(c.significant for c in ev.comparisons)

    unsupported_comparisons: list[str] = []
    causal_without_evidence: list[str] = []

    for sentence in sentences:
        if contains_any_marker(sentence, cfg.comparative_markers_vi) and not has_significant_comparison:
            unsupported_comparisons.append(sentence)

        has_causal = contains_any_marker(sentence, cfg.causal_markers_vi)
        has_correlation_phrase = contains_any_marker(sentence, cfg.correlation_phrases_vi)
        if has_causal and not has_correlation_phrase:
            causal_without_evidence.append(sentence)

    passed = not unsupported_comparisons
    return CheckResult(
        name="stats_guard", passed=passed, score=1.0 if passed else 0.0, severity=Severity.BLOCK,
        details={
            "unsupported_comparisons": unsupported_comparisons,
            "causal_without_evidence": causal_without_evidence,
        },
        message_vi=None if passed else (
            f"{len(unsupported_comparisons)} câu dùng ngôn ngữ so sánh nhưng khác biệt "
            "không có ý nghĩa thống kê (nằm trong sai số)."
        ),
    )


__all__ = ["check_stats_guard"]
