"""Kiem tra app/verify/entity.py::check_entity_grounding - lop L3. Dung
truc tiep catalog THAT (config/semantic/entities.yml, file protected - da
kiem chung) thay vi catalog gia, de test khop dung du lieu san xuat.
Xem docs/17 T09.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.contracts import ColumnSpec, Fact, Severity
from app.semantic.catalog import YamlCatalog, get_catalog
from app.semantic.evidence import EvidenceSet
from app.verify.config import get_verify_config
from app.verify.entity import check_entity_grounding


@pytest.fixture(scope="module")
def catalog() -> YamlCatalog:
    return get_catalog()


@pytest.fixture
def evidence() -> EvidenceSet:
    fact = Fact(
        fact_id="F1", title="ROMI theo chien dich", query_id="q1", sql="SELECT ...",
        columns=[
            ColumnSpec(name="campaign_id", label="Chien dich", unit="text", format=""),
            ColumnSpec(name="romi", label="ROMI", unit="ratio", format="0.00"),
        ],
        rows=[{"_ref": "F1.r1", "campaign_id": "CMP-ZL-RL1", "romi": 6.201503}],
        row_count=1,
    )
    return EvidenceSet(
        evidence_id="ev1", generated_at=dt.datetime.now(), data_version="etl_run_1", facts=[fact],
    )


def test_known_campaign_id_from_evidence_passes(evidence: EvidenceSet, catalog: YamlCatalog) -> None:
    """CMP-ZL-RL1 nam trong chinh evidence (gia tri o cot campaign_id) -> biet."""
    result = check_entity_grounding("Chiến dịch {{F1.r1.campaign_id}} đang hiệu quả.", evidence, catalog)
    assert result.passed, result.details
    assert result.severity == Severity.BLOCK
    assert result.details["unknown_entities"] == []


def test_fabricated_campaign_id_not_in_allowed_values_blocks(
    evidence: EvidenceSet, catalog: YamlCatalog,
) -> None:
    """CMP-FB-002 dung dinh dang ma dinh danh nhung KHONG co trong danh sach
    that (chi co CMP-FB-001) - dung nhu vi du bia trong docstring cua entity.py."""
    result = check_entity_grounding("Chiến dịch CMP-FB-002 đang dẫn đầu.", evidence, catalog)
    assert not result.passed
    assert result.severity == Severity.BLOCK
    assert "CMP-FB-002" in result.details["unknown_entities"]


def test_known_two_word_title_case_phrase_passes(evidence: EvidenceSet, catalog: YamlCatalog) -> None:
    """"Broker Network" la mot channel that trong catalog (2 tu lien tiep
    viet hoa chu dau)."""
    result = check_entity_grounding(
        "Kênh Broker Network có chi phí trên mỗi lead cao.", evidence, catalog,
    )
    assert result.passed, result.details


def test_fabricated_two_word_title_case_phrase_blocks(
    evidence: EvidenceSet, catalog: YamlCatalog,
) -> None:
    """"Instagram Stories" khong xuat hien o bat ky dau trong catalog/evidence
    - dung nhu vi du bia dung trong docstring cua entity.py."""
    result = check_entity_grounding(
        "Chiến dịch Instagram Stories tăng trưởng tốt.", evidence, catalog,
    )
    assert not result.passed
    assert "Instagram Stories" in result.details["unknown_entities"]


def test_single_capitalized_word_is_ignored_by_heuristic(
    evidence: EvidenceSet, catalog: YamlCatalog,
) -> None:
    """Mot tu viet hoa DON LE (vi du "ROMI") bi bo qua co y (xem docstring
    extract_proper_nouns_vi) - khong duoc tinh la thuc thi can kiem chung."""
    result = check_entity_grounding(
        "ROMI của {{F1.r1.campaign_id}} là 6,20.", evidence, catalog,
    )
    assert result.passed, result.details
    assert "ROMI" not in result.details["mentioned"]


def test_fuzzy_typo_within_threshold_still_passes(evidence: EvidenceSet, catalog: YamlCatalog) -> None:
    """Loi go nho (thieu 1 chu) van trong nguong fuzzy 0,92 cua config/verify.yaml."""
    cfg = get_verify_config()
    assert cfg.entity_fuzzy_threshold == pytest.approx(0.92)
    result = check_entity_grounding(
        "Kênh Broker Netwrk có chi phí trên mỗi lead cao.", evidence, catalog,
    )
    assert result.passed, result.details


def test_no_proper_nouns_gives_score_one(evidence: EvidenceSet, catalog: YamlCatalog) -> None:
    result = check_entity_grounding("Chưa có bằng chứng cụ thể cho câu hỏi này.", evidence, catalog)
    assert result.passed
    assert result.score == pytest.approx(1.0)
