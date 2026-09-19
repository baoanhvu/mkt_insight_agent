"""Kiem tra app/verify/stats_guard.py::check_stats_guard - lop L4, lop DUY
NHAT bat duoc loi "Freelancer sinh lời nhất" (docs/08-anti-hallucination.md
muc 8.4): con so 220.200 la THAT trong ket qua truy van, nhung chenh lech
giua 7 nhom nghe nghiep nam trong sai so thong ke (ANOVA p=0,9718) - khong
lop grounding so/thuc the nao khac bat duoc dieu nay. Xem docs/17 T09.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.contracts import Comparison, Severity
from app.semantic.evidence import EvidenceSet
from app.verify.stats_guard import check_stats_guard


def _make_evidence(comparisons: list[Comparison]) -> EvidenceSet:
    return EvidenceSet(
        evidence_id="ev1", generated_at=dt.datetime.now(), data_version="etl_run_1",
        comparisons=comparisons,
    )


_NOT_SIGNIFICANT = Comparison(
    left="F1.r1", right="F1.r2", metric="profit_avg", diff=220_200.0, p_value=0.9718,
    ci=(-50_000.0, 490_000.0), effect_size=0.02, n_left=284, n_right=210, significant=False,
    verdict_vi="Chenh lech nam trong sai so thong ke (p=0,9718).",
)

_SIGNIFICANT = Comparison(
    left="F1.r1", right="F1.r2", metric="romi", diff=4.6, p_value=0.001,
    ci=(3.9, 5.3), effect_size=0.8, n_left=1200, n_right=1100, significant=True,
    verdict_vi="Khac biet co y nghia thong ke (p=0,001).",
)


def test_comparative_language_without_significant_comparison_blocks() -> None:
    """Cau hoi vang cua du an: "Freelancer sinh lời nhất" khi ANOVA
    significant=False PHAI bi chan (docs/17 muc T09, dong cuoi CLAUDE.md)."""
    ev = _make_evidence([_NOT_SIGNIFICANT])
    result = check_stats_guard("Nhóm nghề Freelancer sinh lời nhất trong kỳ.", ev)
    assert not result.passed
    assert result.severity == Severity.BLOCK
    assert len(result.details["unsupported_comparisons"]) == 1


def test_comparative_language_with_significant_comparison_passes() -> None:
    ev = _make_evidence([_SIGNIFICANT])
    result = check_stats_guard("Chiến dịch CMP-ZL-RL1 có ROMI cao hơn hẳn các chiến dịch còn lại.", ev)
    assert result.passed, result.details
    assert result.details["unsupported_comparisons"] == []


def test_no_significant_comparison_at_all_blocks_comparative_sentence() -> None:
    """Khong co Comparison nao ca (rong) van phai chan neu cau dung marker so sanh."""
    ev = _make_evidence([])
    result = check_stats_guard("Chiến dịch này tốt nhất trong toàn bộ danh mục.", ev)
    assert not result.passed


def test_sentence_without_comparative_marker_always_passes() -> None:
    ev = _make_evidence([])
    result = check_stats_guard("ROMI của chiến dịch này là 6,20.", ev)
    assert result.passed
    assert result.details["unsupported_comparisons"] == []


def test_causal_marker_without_correlation_phrase_is_flagged_but_not_blocking() -> None:
    """Cau nhan qua ("làm tăng") khi khong co nguon nhan qua (khong co
    causal_evidence_sources trong PoC nay) duoc GHI NHAN o
    causal_without_evidence nhung KHONG tu no lam BLOCK - do la WARN theo
    config/verify.yaml (chi rieng so sanh hon-kem moi la BLOCK o lop nay)."""
    ev = _make_evidence([])
    result = check_stats_guard("Chi phí quảng cáo thấp làm tăng ROMI của chiến dịch.", ev)
    assert len(result.details["causal_without_evidence"]) == 1
    assert result.passed  # khong co marker so sanh hon-kem nen van pass o lop nay


def test_causal_marker_with_correlation_phrase_is_not_flagged() -> None:
    ev = _make_evidence([])
    result = check_stats_guard(
        "Chi phí quảng cáo thấp đi cùng với ROMI cao hơn ở nhóm này.", ev,
    )
    assert result.details["causal_without_evidence"] == []


@pytest.mark.parametrize("sentence", [
    "Chiến dịch A có ROMI gấp đôi chiến dịch B.",
    "Broker Network kém hiệu quả hơn Zalo Remarketing.",
    "Đây là chiến dịch dẫn đầu về lợi nhuận.",
])
def test_various_comparative_markers_are_detected(sentence: str) -> None:
    ev = _make_evidence([])
    result = check_stats_guard(sentence, ev)
    assert not result.passed, f"cau '{sentence}' phai bi chan vi khong co Comparison significant=True"
