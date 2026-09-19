"""Kiem tra app/verify/numeric.py::check_numeric_grounding - lop L2, quan
trong nhat trong toan bo he thong (CLAUDE.md R1). Xem docs/17 T09.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.contracts import ColumnSpec, Fact, Severity
from app.semantic.evidence import EvidenceSet
from app.verify.config import get_verify_config
from app.verify.numeric import check_numeric_grounding


@pytest.fixture
def evidence() -> EvidenceSet:
    fact = Fact(
        fact_id="F1", title="ROMI theo chien dich", query_id="q1", sql="SELECT ...",
        columns=[
            ColumnSpec(name="campaign_id", label="Chien dich", unit="text", format=""),
            ColumnSpec(name="romi", label="ROMI", unit="ratio", format="0.00"),
            ColumnSpec(name="ty_le_duyet", label="Ty le duyet", unit="percent", format="0.0%"),
            ColumnSpec(name="loi_nhuan", label="Loi nhuan", unit="vnd", format="#,##0"),
        ],
        rows=[
            {
                "_ref": "F1.r1", "campaign_id": "CMP-ZL-RL1", "romi": 6.201503,
                "ty_le_duyet": 0.488, "loi_nhuan": 392498488.0,
            },
        ],
        row_count=1,
    )
    return EvidenceSet(
        evidence_id="ev1", generated_at=dt.datetime.now(), data_version="etl_run_1", facts=[fact],
    )


def test_resolved_tag_passes(evidence: EvidenceSet) -> None:
    result = check_numeric_grounding("ROMI của {{F1.r1.romi}}.", evidence)
    assert result.passed
    assert result.score == pytest.approx(1.0)
    assert result.severity == Severity.BLOCK  # muc do khi HONG, khong phai khi qua
    assert result.details["unresolved_tags"] == []


def test_unresolved_tag_blocks(evidence: EvidenceSet) -> None:
    """The {{F9.r1.romi}} khong ton tai trong evidence -> passed=False."""
    result = check_numeric_grounding("ROMI của {{F9.r1.romi}}.", evidence)
    assert not result.passed
    assert result.severity == Severity.BLOCK
    assert "F9.r1.romi" in result.details["unresolved_tags"]


def test_bare_number_not_matching_any_cell_blocks(evidence: EvidenceSet) -> None:
    """So tran KHONG khop bat ky o nao trong evidence -> passed=False."""
    result = check_numeric_grounding("ROMI của chiến dịch này là 99,99.", evidence)
    assert not result.passed
    assert "99,99" in result.details["ungrounded_numbers"]


def test_bare_number_matching_a_cell_still_passes(evidence: EvidenceSet) -> None:
    """So viet thang nhung DUNG (khop mot o trong evidence) khong bi chan o
    lop nay - day la xap xi hop ly duoc ghi ro trong docstring cua numeric.py."""
    result = check_numeric_grounding("ROMI của chiến dịch này là 6,20.", evidence)
    assert result.passed
    assert result.details["ungrounded_numbers"] == []


def test_percent_string_matches_ratio_cell_via_percent_policy(evidence: EvidenceSet) -> None:
    """"48,8%" -> parse_vi_number chia 100 thanh 0,488 -> khop cell ty_le_duyet
    (luu la ratio 0..1) qua chinh sach 'percent'."""
    result = check_numeric_grounding("Tỷ lệ duyệt là 48,8%.", evidence)
    assert result.passed
    assert result.details["ungrounded_numbers"] == []


def test_billion_suffix_matches_vnd_cell(evidence: EvidenceSet) -> None:
    """"1,2 tỷ" phai quy doi thanh 1_200_000_000 va thu khop - o day khong co
    cell nao dung gia tri do nen PHAI bi chan (kiem tra ca chieu am: neu vo
    tinh luon "match" moi thu thi lop nay vo dung)."""
    result = check_numeric_grounding("Doanh thu ước tính 1,2 tỷ.", evidence)
    assert not result.passed
    assert "1,2 tỷ" in result.details["ungrounded_numbers"]


def test_billion_suffix_matches_when_cell_has_that_exact_value() -> None:
    fact = Fact(
        fact_id="F2", title="Doanh thu", query_id="q2", sql="SELECT ...",
        columns=[ColumnSpec(name="doanh_thu", label="Doanh thu", unit="vnd", format="#,##0")],
        rows=[{"_ref": "F2.r1", "doanh_thu": 1_200_000_000.0}],
        row_count=1,
    )
    ev = EvidenceSet(
        evidence_id="ev2", generated_at=dt.datetime.now(), data_version="etl_run_1", facts=[fact],
    )
    result = check_numeric_grounding("Doanh thu ước tính 1,2 tỷ.", ev)
    assert result.passed
    assert result.details["ungrounded_numbers"] == []


@pytest.mark.parametrize("text", [
    "Năm 2026 tăng trưởng tốt.",       # nam - allowlist years
    "Top 5 chiến dịch hiệu quả nhất.",  # thu tu - allowlist ordinals
    "Có 0 hồ sơ trong nhóm này.",       # literal allowlist
    "Có 1 chiến dịch dẫn đầu.",         # literal allowlist
])
def test_allowlisted_numbers_never_block(text: str, evidence: EvidenceSet) -> None:
    result = check_numeric_grounding(text, evidence)
    assert result.passed, result.details


def test_no_tags_and_no_bare_numbers_gives_rate_one(evidence: EvidenceSet) -> None:
    """Khong co the, khong co so tran -> rate = 1,0 mot cach vo tinh (total=0)."""
    result = check_numeric_grounding("Chưa có bằng chứng cụ thể cho câu hỏi này.", evidence)
    assert result.passed
    assert result.score == pytest.approx(1.0)


def test_id_like_string_is_not_flagged_as_bare_number(evidence: EvidenceSet) -> None:
    """CMP-ZL-RL1 chua chu so nhung la ma dinh danh, khong phai so - khong
    duoc dua vao danh sach so tran can khop."""
    result = check_numeric_grounding("Chiến dịch CMP-ZL-RL1 đang hiệu quả.", evidence)
    assert result.passed
    assert result.details["ungrounded_numbers"] == []


def test_decimal_cell_value_from_real_postgres_numeric_is_handled() -> None:
    """Hoi quy: cot NUMERIC cua Postgres tra ve qua psycopg/SQLAlchemy duoi
    dang decimal.Decimal, khong phai float - lop nay PHAI nhan dien duoc,
    neu khong moi so tien/ty le lay tu DB thuc se luon bi bao 'ungrounded'."""
    from decimal import Decimal

    fact = Fact(
        fact_id="F3", title="ROMI", query_id="q3", sql="SELECT ...",
        columns=[ColumnSpec(name="romi", label="ROMI", unit="ratio", format="0.00")],
        rows=[{"_ref": "F3.r1", "romi": Decimal("-1.85")}],
        row_count=1,
    )
    ev = EvidenceSet(
        evidence_id="ev3", generated_at=dt.datetime.now(), data_version="etl_run_1", facts=[fact],
    )
    result = check_numeric_grounding("ROMI của chiến dịch này là -1,85.", ev)
    assert result.passed, result.details


def test_matches_any_cell_direct_via_evidence(evidence: EvidenceSet) -> None:
    """Kiem tra truc tiep EvidenceSet.matches_any_cell voi tung chinh sach da
    khai bao trong config/verify.yaml, khong qua check_numeric_grounding."""
    cfg = get_verify_config()
    ratio_policy = cfg.numeric_policies["ratio"]
    from app.verify.numeric import _to_numeric_policy

    policy = _to_numeric_policy(cfg, "ratio")
    assert evidence.matches_any_cell(6.201503, policy)
    assert not evidence.matches_any_cell(999.99, policy)
    assert ratio_policy.mode == "round"
