"""Kiem tra app/analytics/derive.py - dac biet la an toan cua bo phan tich AST
(khong bao gio dung eval() tren chuoi tuy y)."""

from __future__ import annotations

import datetime as dt

import pytest

from app.analytics.derive import DerivedExprError, compute_derived
from app.contracts import ColumnSpec, Fact
from app.semantic.evidence import EvidenceSet


@pytest.fixture
def evidence() -> EvidenceSet:
    fact = Fact(
        fact_id="F1", title="ROMI theo chien dich", query_id="q1", sql="SELECT ...",
        columns=[
            ColumnSpec(name="campaign_id", label="Chien dich", unit="text", format=""),
            ColumnSpec(name="romi", label="ROMI", unit="ratio", format="0.00"),
        ],
        rows=[
            {"_ref": "F1.r1", "campaign_id": "CMP-ZL-RL1", "romi": 6.201503},
            {"_ref": "F1.r2", "campaign_id": "CMP-GG-001", "romi": 1.601062},
        ],
        row_count=2,
    )
    return EvidenceSet(
        evidence_id="ev1", generated_at=dt.datetime.now(), data_version="etl_run_1",
        facts=[fact],
    )


def test_compute_derived_division(evidence: EvidenceSet) -> None:
    d = compute_derived(
        "F1.r1.romi / F1.r2.romi", evidence, fact_id="D1",
        label_vi="Zalo gap Google bao nhieu lan ve ROMI",
    )
    assert d.value == pytest.approx(6.201503 / 1.601062)
    assert d.formatted == format(d.value, ".2f").replace(".", ",")


def test_compute_derived_subtraction_and_constant(evidence: EvidenceSet) -> None:
    d = compute_derived("F1.r1.romi - 1.0", evidence, fact_id="D2", label_vi="Chenh lech")
    assert d.value == pytest.approx(6.201503 - 1.0)


def test_compute_derived_unary_minus(evidence: EvidenceSet) -> None:
    d = compute_derived("-F1.r1.romi", evidence, fact_id="D3", label_vi="Am")
    assert d.value == pytest.approx(-6.201503)


def test_compute_derived_unresolvable_ref_raises(evidence: EvidenceSet) -> None:
    with pytest.raises(DerivedExprError):
        compute_derived("F9.r1.romi / 2", evidence, fact_id="D4", label_vi="x")


def test_compute_derived_division_by_zero_raises(evidence: EvidenceSet) -> None:
    with pytest.raises(DerivedExprError):
        compute_derived("F1.r1.romi / 0", evidence, fact_id="D5", label_vi="x")


def test_compute_derived_rejects_arbitrary_code() -> None:
    """Khong duoc thuc thi bat ky thu gi ngoai +,-,*,/ va tham chieu - dam bao
    KHONG dung eval() tren chuoi tuy y (goi ham, import, comprehension...)."""
    evidence_empty = EvidenceSet(
        evidence_id="ev2", generated_at=dt.datetime.now(), data_version="etl_run_1",
    )
    for malicious_expr in (
        "__import__('os').system('echo pwned')",
        "[x for x in range(10)]",
        "open('secrets.yaml').read()",
        "1 if True else 2",
    ):
        with pytest.raises(DerivedExprError):
            compute_derived(malicious_expr, evidence_empty, fact_id="D6", label_vi="x")


def test_compute_derived_syntax_error_raises(evidence: EvidenceSet) -> None:
    with pytest.raises(DerivedExprError):
        compute_derived("F1.r1.romi / ", evidence, fact_id="D7", label_vi="x")
