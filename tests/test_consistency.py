"""Kiem tra app/verify/consistency.py::compute_self_consistency - self-
consistency cho duong freeform (T12, chua kich hoat). Xem docs/17 T11.
"""

from __future__ import annotations

import pytest

from app.verify.consistency import compute_self_consistency

_ALIASES = {"tỷ": 1_000_000_000.0, "triệu": 1_000_000.0}


def test_identical_answers_give_full_top_cluster_share() -> None:
    answers = ["ROMI đạt 6,20."] * 5
    result = compute_self_consistency(answers, _ALIASES)
    assert result.top_cluster_share == 1.0
    assert result.n_samples == 5
    assert result.n_clusters == 1


def test_disagreeing_numbers_lower_the_top_cluster_share() -> None:
    """3 lan hoi ra 3 con so KHAC nhau -> moi lan la mot cum rieng, ty trong
    cum lon nhat chi 1/3 - dau hieu model dang doan chu khong doc du lieu."""
    answers = ["ROMI đạt 6,20.", "ROMI đạt 1,60.", "ROMI đạt 0,67."]
    result = compute_self_consistency(answers, _ALIASES)
    assert result.top_cluster_share == pytest.approx(1 / 3)
    assert result.n_clusters == 3


def test_majority_cluster_wins_when_two_of_three_agree() -> None:
    answers = ["ROMI đạt 6,20.", "ROMI đạt 6,20.", "ROMI đạt 1,60."]
    result = compute_self_consistency(answers, _ALIASES)
    assert result.top_cluster_share == pytest.approx(2 / 3)
    assert result.n_clusters == 2


def test_answers_with_unit_suffix_normalize_to_same_fingerprint() -> None:
    """"1,2 tỷ" va "1200000000" phai duoc coi la CUNG mot con so (dau van
    tay dua tren gia tri da quy doi, khong phai chuoi tho)."""
    answers = ["Doanh thu ước tính 1,2 tỷ.", "Doanh thu ước tính 1.200.000.000."]
    result = compute_self_consistency(answers, _ALIASES)
    assert result.top_cluster_share == 1.0


def test_no_bare_numbers_still_clusters_by_empty_fingerprint() -> None:
    answers = ["Chưa đủ dữ liệu để kết luận."] * 3
    result = compute_self_consistency(answers)
    assert result.top_cluster_share == 1.0


def test_empty_answers_list_returns_zero_share_not_crash() -> None:
    result = compute_self_consistency([])
    assert result.top_cluster_share == 0.0
    assert result.n_samples == 0

