"""L3 - Entity grounding. Xem docs/08-anti-hallucination.md muc 8.5."""

from __future__ import annotations

import difflib

from app.contracts import CheckResult, Severity
from app.semantic.catalog import YamlCatalog
from app.semantic.evidence import EvidenceSet
from app.verify.config import VerifyConfig, get_verify_config
from app.verify.vi_text import extract_proper_nouns_vi


def _fuzzy_in(candidate: str, known: set[str], threshold: float) -> bool:
    if candidate in known:
        return True
    return bool(difflib.get_close_matches(candidate, known, n=1, cutoff=threshold))


def _drop_leading_words_variants(phrase: str) -> list[str]:
    """Cau tieng Viet LUON viet hoa chu dau cau, bat ke tu do co phai ten
    rieng hay khong - vi vay mot ten rieng THAT (vi du "Broker Network") dung
    ngay sau tu dau cau ("Kênh Broker Network...") se bi _find_title_sequences
    gop nham thanh mot chuoi dai hon khong khop catalog. Thu bo dan tung tu
    dau de tim phan duoi co the la ten rieng that truoc khi ket luan bia."""
    words = phrase.split(" ")
    return [" ".join(words[i:]) for i in range(1, len(words))]


def _is_known(candidate: str, known: set[str], threshold: float) -> bool:
    if _fuzzy_in(candidate, known, threshold):
        return True
    return any(_fuzzy_in(v, known, threshold) for v in _drop_leading_words_variants(candidate))


def check_entity_grounding(
    text: str, ev: EvidenceSet, catalog: YamlCatalog, cfg: VerifyConfig | None = None,
) -> CheckResult:
    """Moi ten rieng xuat hien trong cau tra loi PHAI co thuc - bat duoc loi
    bia "chien dich Instagram Stories" hay nham CMP-FB-002 (chi co -001)."""
    cfg = cfg or get_verify_config()
    known = ev.all_string_values() | catalog.all_dimension_values()

    rendered_text, _ = ev.substitute(text)
    mentioned = extract_proper_nouns_vi(rendered_text, cfg.id_patterns)

    unknown = sorted(m for m in mentioned if not _is_known(m, known, cfg.entity_fuzzy_threshold))
    passed = not unknown
    score = 1.0 - (len(unknown) / max(len(mentioned), 1))

    return CheckResult(
        name="entity_grounding", passed=passed, score=score, severity=Severity.BLOCK,
        details={"mentioned": sorted(mentioned), "unknown_entities": unknown},
        message_vi=None if passed else f"Nhắc tới thực thể không có trong dữ liệu: {unknown}",
    )


__all__ = ["check_entity_grounding"]
