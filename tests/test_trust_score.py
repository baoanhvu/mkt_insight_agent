"""Kiem tra app/verify/pipeline.py::compute_trust - L6 (Trust Score). Xem
docs/08-anti-hallucination.md muc 8.7 va docs/17 T11.

BAT BUOC (docs/17 T11): hard_fail -> trust = 0.0 bat ke cac diem khac.
"""

from __future__ import annotations

import pytest

from app.contracts import Band, CheckResult, Decision, JudgeResult, Severity
from app.verify.config import get_verify_config
from app.verify.judge import judge_to_check_result
from app.verify.pipeline import band_to_decision, compute_trust


def _check(name: str, *, passed: bool, score: float, severity: Severity = Severity.BLOCK) -> CheckResult:
    return CheckResult(name=name, passed=passed, score=score, severity=severity)


def test_hard_fail_forces_zero_regardless_of_other_high_scores() -> None:
    """BAT BUOC: mot muc BLOCK fail (o day: numeric_grounding) -> trust = 0.0
    DU cac muc khac deu diem tuyet doi 1.0."""
    checks = [
        _check("numeric_grounding", passed=False, score=0.0),
        _check("entity_grounding", passed=True, score=1.0),
        _check("stats_guard", passed=True, score=1.0),
    ]
    trust = compute_trust(checks)
    assert trust.value == 0.0
    assert trust.band == Band.BLOCKED
    assert band_to_decision(trust.band) == Decision.BLOCKED


def test_judge_contradiction_is_also_a_hard_fail() -> None:
    """`judge_to_check_result` bien JudgeResult co contradiction_rate > 0
    thanh mot CheckResult severity=BLOCK, passed=False - hoa chung vao tap
    hard-fail giong het L2/L3/L4, dung theo bang anh xa cua docs 8.6."""
    judge = JudgeResult(
        entailment_rate=0.5, neutral_rate=0.0, contradiction_rate=0.5, grounding_score=0.0,
    )
    checks = [
        _check("numeric_grounding", passed=True, score=1.0),
        _check("entity_grounding", passed=True, score=1.0),
        _check("stats_guard", passed=True, score=1.0),
        judge_to_check_result(judge),
    ]
    trust = compute_trust(checks)
    assert trust.value == 0.0
    assert trust.band == Band.BLOCKED
    assert "judge" in [c.name for c in checks if not c.passed]


def test_all_checks_pass_with_high_scores_gives_pass_band() -> None:
    cfg = get_verify_config()
    judge = JudgeResult(entailment_rate=1.0, neutral_rate=0.0, contradiction_rate=0.0, grounding_score=1.0)
    checks = [
        _check("numeric_grounding", passed=True, score=1.0),
        _check("entity_grounding", passed=True, score=1.0),
        _check("stats_guard", passed=True, score=1.0),
        judge_to_check_result(judge),
    ]
    trust = compute_trust(checks)
    assert trust.value == pytest.approx(1.0)
    assert trust.value >= cfg.t_high
    assert trust.band == Band.PASS
    assert band_to_decision(trust.band) == Decision.ANSWERED


def test_low_judge_entailment_pulls_band_down_without_hard_fail() -> None:
    """Judge khong mau thuan (contradiction_rate=0) nhung entailment thap
    (nhieu NOT_ENOUGH_INFO) -> khong hard-fail, nhung diem trong so keo band
    xuong HEDGE/ABSTAIN thay vi PASS - dung tinh than "neutral_rate cao ->
    HEDGE" cua docs 8.6, thuc hien qua trong so thay vi mot nhanh rieng."""
    judge = JudgeResult(entailment_rate=0.2, neutral_rate=0.8, contradiction_rate=0.0, grounding_score=0.2)
    checks = [
        _check("numeric_grounding", passed=True, score=1.0),
        _check("entity_grounding", passed=True, score=1.0),
        _check("stats_guard", passed=True, score=1.0),
        judge_to_check_result(judge),
    ]
    trust = compute_trust(checks)
    assert trust.band != Band.PASS
    assert trust.value < 1.0


def test_no_checks_at_all_abstains() -> None:
    trust = compute_trust([])
    assert trust.value == 0.0
    assert trust.band == Band.ABSTAIN
    assert band_to_decision(trust.band) == Decision.ABSTAINED


@pytest.mark.parametrize("band,decision", [
    (Band.PASS, Decision.ANSWERED), (Band.HEDGE, Decision.HEDGED),
    (Band.ABSTAIN, Decision.ABSTAINED), (Band.BLOCKED, Decision.BLOCKED),
])
def test_band_to_decision_mapping(band: Band, decision: Decision) -> None:
    assert band_to_decision(band) == decision
