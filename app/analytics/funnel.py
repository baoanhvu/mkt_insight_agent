"""Pheu chuyen doi cho D1: lead -> ho so -> giai ngan.

CANH BAO BAT BUOC (DQ-04, docs/02-data-model.md muc 2.1): khong co khoa noi
giua `fact_lead` va `fact_loan`. Moi ty le tinh tu day la TY LE TONG HOP muc
chien dich (dem doc lap roi chia), KHONG phai attribution tung lead.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.analytics.stats import wilson_ci


@dataclass(frozen=True, slots=True)
class FunnelStage:
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class FunnelStep:
    from_stage: str
    to_stage: str
    from_count: int
    to_count: int
    rate: float | None
    rate_ci: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class FunnelResult:
    stages: tuple[FunnelStage, ...]
    steps: tuple[FunnelStep, ...]

    def step(self, from_stage: str, to_stage: str) -> FunnelStep:
        for s in self.steps:
            if s.from_stage == from_stage and s.to_stage == to_stage:
                return s
        raise KeyError(f"khong co buoc pheu '{from_stage}' -> '{to_stage}'")


def _rate_and_ci(numerator: int, denominator: int, conf: float) -> tuple[float | None, tuple[float, float] | None]:
    if denominator == 0:
        return None, None
    rate = numerator / denominator
    # wilson_ci yeu cau successes <= n; du lieu vo hieu (numerator > denominator)
    # duoc bao ve o day thay vi de ValueError lam vo cau tra loi.
    successes = min(numerator, denominator)
    return rate, wilson_ci(successes, denominator, conf=conf)


def compute_funnel(
    leads: int, applications: int, disbursed: int, *, conf: float = 0.95
) -> FunnelResult:
    """`leads`/`applications`/`disbursed` la TONG cua ky va lat cat dang xet
    (thuong lay tu `mart.mart_campaign_daily`, dem doc lap theo dung DQ-04)."""
    stages = (
        FunnelStage("leads", leads),
        FunnelStage("applications", applications),
        FunnelStage("disbursed", disbursed),
    )
    pairs = (
        ("leads", leads, "applications", applications),
        ("applications", applications, "disbursed", disbursed),
        ("leads", leads, "disbursed", disbursed),
    )
    steps = []
    for a_name, a_n, b_name, b_n in pairs:
        rate, ci = _rate_and_ci(b_n, a_n, conf)
        steps.append(FunnelStep(from_stage=a_name, to_stage=b_name, from_count=a_n,
                                 to_count=b_n, rate=rate, rate_ci=ci))
    return FunnelResult(stages=stages, steps=tuple(steps))


__all__ = ["FunnelStage", "FunnelStep", "FunnelResult", "compute_funnel"]
