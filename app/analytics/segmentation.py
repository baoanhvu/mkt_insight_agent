"""Phan khuc khach hang bang LUAT TUONG MINH - khong LLM, khong k-means cho
duong tra loi that. Dinh nghia goc: config/analytics.yaml -> segmentation.rules.
Ban sao SQL tuong duong: etl/sql/02_ddl_mart.sql -> mart.v_customer_segment.

THU TU RULE LA DAC TA, khong duoc sap xep lai: moi khach roi vao phan khuc
DAU TIEN khop. `high_risk` PHAI dung dau vi rui ro ghi de moi thuoc tinh khac
- ban dau no dung cuoi va chi bat duoc 15/97 khach (xem canh bao trong
docs/06-agent-design.md muc 6.6 va ADR-004).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from app.analytics.config import AnalyticsConfig, get_analytics_config

_UNCLASSIFIED = "_unclassified"


@dataclass(frozen=True, slots=True)
class CustomerRow:
    """Truong toi thieu de phan khuc mot khach - khop cot cua
    `mart.mart_customer_value`."""

    customer_id: str
    n_applications: int
    n_disbursed: int
    n_rejected: int
    is_repeat_customer: bool
    is_never_applied: bool
    has_app: bool
    income_band: str
    profit_to_date: float
    worst_dayslate: int | None = None


def _rule_high_risk(c: CustomerRow, profit_p75: float) -> bool:
    return (c.worst_dayslate or 0) > 30 or c.n_rejected >= 2


def _rule_champion(c: CustomerRow, profit_p75: float) -> bool:
    return c.is_repeat_customer and c.profit_to_date >= profit_p75


def _rule_repeat_standard(c: CustomerRow, profit_p75: float) -> bool:
    return c.is_repeat_customer


def _rule_high_potential(c: CustomerRow, profit_p75: float) -> bool:
    return (
        c.n_disbursed >= 1
        and c.income_band in ("12-20M", ">=20M")
        and c.has_app
        and (c.worst_dayslate or 0) == 0
    )


def _rule_app_gap(c: CustomerRow, profit_p75: float) -> bool:
    return c.n_disbursed >= 1 and not c.has_app and c.income_band in ("12-20M", ">=20M")


def _rule_dormant(c: CustomerRow, profit_p75: float) -> bool:
    return c.n_disbursed >= 1


def _rule_rejected_only(c: CustomerRow, profit_p75: float) -> bool:
    return c.n_applications >= 1


def _rule_never_activated(c: CustomerRow, profit_p75: float) -> bool:
    return c.is_never_applied


# THU TU nay chinh la dac ta (docs/06 muc 6.6). Khong sap xep lai.
_SEGMENT_RULES: tuple[tuple[str, Callable[[CustomerRow, float], bool]], ...] = (
    ("high_risk", _rule_high_risk),
    ("champion", _rule_champion),
    ("repeat_standard", _rule_repeat_standard),
    ("high_potential", _rule_high_potential),
    ("app_gap", _rule_app_gap),
    ("dormant", _rule_dormant),
    ("rejected_only", _rule_rejected_only),
    ("never_activated", _rule_never_activated),
)


def compute_profit_p75(customers: Sequence[CustomerRow]) -> float:
    """Percentile 75 cua `profit_to_date`, CHI tren khach co `n_applications > 0`
    - khop dieu kien CTE `p75` trong mart.v_customer_segment. Tra 0.0 neu
    khong co khach nao da nop ho so (truong hop rong, khong nen xay ra tren
    du lieu that nhung tranh chia cho tap rong)."""
    applied = [c.profit_to_date for c in customers if c.n_applications > 0]
    if not applied:
        return 0.0
    return float(np.percentile(applied, 75))


def classify_customer(c: CustomerRow, profit_p75: float) -> str:
    """Tra ve id phan khuc DAU TIEN khop. `_unclassified` la tin hieu LOI BO
    LUAT (xem test_no_unclassified) - KHONG BAO GIO duoc xuat hien tren du
    lieu that; neu xuat hien, bo luat con thieu mot nhanh."""
    for seg_id, predicate in _SEGMENT_RULES:
        if predicate(c, profit_p75):
            return seg_id
    return _UNCLASSIFIED


@dataclass(frozen=True, slots=True)
class SegmentDistribution:
    total: int
    unclassified: int
    counts: dict[str, int] = field(default_factory=dict)

    def share(self, segment_id: str) -> float:
        return self.counts.get(segment_id, 0) / self.total if self.total else 0.0


def segment_all(
    customers: Sequence[CustomerRow],
) -> tuple[dict[str, str], SegmentDistribution]:
    """Phan khuc toan bo khach. Tra ve (customer_id -> segment_id, phan bo)."""
    profit_p75 = compute_profit_p75(customers)
    assignments: dict[str, str] = {}
    counts: dict[str, int] = {}
    for c in customers:
        seg = classify_customer(c, profit_p75)
        assignments[c.customer_id] = seg
        counts[seg] = counts.get(seg, 0) + 1
    return assignments, SegmentDistribution(
        total=len(customers), unclassified=counts.get(_UNCLASSIFIED, 0), counts=counts
    )


def segment_rule_order(cfg: AnalyticsConfig | None = None) -> tuple[str, ...]:
    """Thu tu id phan khuc theo dung `config/analytics.yaml` - dung de kiem
    tra code va cau hinh KHONG troi nhau (tests/test_segmentation.py)."""
    cfg = cfg or get_analytics_config()
    return cfg.segment_rule_ids


# =============================================================================
# Che do doi chung tuy chon (docs/06 muc 6.6: "--mode kmeans"). KHONG BAO GIO
# la nguon cho cau tra loi that - chi dung de kiem tra bo luat thu cong co bo
# sot cau truc nao khong. scikit-learn KHONG nam trong requirements.txt chinh
# (chi trong requirements-dev.txt) vi ly do do.
# =============================================================================

def kmeans_reference_segments(
    customers: Sequence[CustomerRow], n_clusters: int = 8, seed: int = 42,
) -> dict[str, int]:
    """Gan mot nhan cum (0..n_clusters-1) cho moi khach, dua tren
    (profit_to_date, n_disbursed, is_repeat_customer, has_app). CHI dung de
    doi chung bo luat thu cong (`segment_all`), khong bao gio hien thi truc
    tiep cho nguoi dung."""
    from sklearn.cluster import KMeans  # import cuc bo: phu thuoc [dev] tuy chon

    features = np.array(
        [
            [
                c.profit_to_date,
                float(c.n_disbursed),
                1.0 if c.is_repeat_customer else 0.0,
                1.0 if c.has_app else 0.0,
            ]
            for c in customers
        ]
    )
    # Chuan hoa don gian (z-score) de profit_to_date (thang trieu VND) khong
    # lam lu mo ba dac trung boolean/count con lai.
    std = features.std(axis=0)
    std[std == 0] = 1.0
    normalized = (features - features.mean(axis=0)) / std

    model = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    labels = model.fit_predict(normalized)
    return {c.customer_id: int(lbl) for c, lbl in zip(customers, labels, strict=True)}


__all__ = [
    "CustomerRow", "SegmentDistribution", "classify_customer", "compute_profit_p75",
    "segment_all", "segment_rule_order", "kmeans_reference_segments",
]
