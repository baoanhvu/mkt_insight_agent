"""Kiem tra app/analytics/funnel.py - ham thuan, khong can DB."""

from __future__ import annotations

import pytest

from app.analytics.funnel import compute_funnel


def test_funnel_basic_rates() -> None:
    result = compute_funnel(leads=1000, applications=300, disbursed=180)
    step1 = result.step("leads", "applications")
    step2 = result.step("applications", "disbursed")
    step3 = result.step("leads", "disbursed")

    assert step1.rate == pytest.approx(0.30)
    assert step2.rate == pytest.approx(0.60)
    assert step3.rate == pytest.approx(0.18)
    assert step1.rate_ci is not None and step1.rate_ci[0] < step1.rate < step1.rate_ci[1]


def test_funnel_handles_zero_leads_without_crashing() -> None:
    result = compute_funnel(leads=0, applications=0, disbursed=0)
    step = result.step("leads", "applications")
    assert step.rate is None
    assert step.rate_ci is None


def test_funnel_step_lookup_raises_for_unknown_pair() -> None:
    result = compute_funnel(leads=100, applications=50, disbursed=20)
    with pytest.raises(KeyError):
        result.step("disbursed", "leads")


def test_funnel_matches_zalo_reference_scale() -> None:
    """Doi chieu tho voi ty le duyet cua CMP-ZL-RL1 (92,0%) - dung nhu vi du
    trong config/analytics.yaml -> actions[0].validated.conversion (0,316 lead
    -> ho so, x 92,0% duyet)."""
    result = compute_funnel(leads=486, applications=486, disbursed=447)
    step = result.step("applications", "disbursed")
    assert step.rate == pytest.approx(0.920, abs=0.01)
