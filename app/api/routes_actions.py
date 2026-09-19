"""`/api/actions` - danh sach khuyen nghi D3 (docs/06-agent-design.md muc 6.7).
KHONG GOI LLM: LLM khong duoc phep tu nghi hanh dong, chi CHON trong thu vien
da du dieu kien va giai thich (xem CLAUDE.md).

# ASSUMPTION: `trigger`/`impact_formula` trong config/analytics.yaml -> actions
la mot DSL tu do goi ham `metric()`/`segment_size()`, dung bien tu do 'C' o
hai hanh dong ("ung voi tung chien dich C") nhung KHONG duoc dinh nghia hinh
thuc o dau: khong ro pham vi lap cua 'C', khong ro C co the la danh sach hay
chi mot gia tri. Danh gia tong quat mot DSL chua dac ta ro co rui ro dien
giai sai hon la giup ich. Vi vay moi dieu kien du duoc kiem tra bang MOT HAM
PYTHON RIENG, bam sat dung mo ta tieng Viet cua chinh trigger do, thay vi mot
bo dien giai DSL tong quat. `impact_vnd` lay TRUC TIEP tu khoi `validated`
(da kiem chung tren du lieu that), khong tinh lai qua `impact_formula`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends

from app.analytics.config import ActionSpec, get_analytics_config
from app.api.deps import get_metric_runner
from app.api.routes_segments import build_segment_table
from app.contracts import DateRange, Filter, MetricRequest
from app.data.repository import SqlMetricRunner

router = APIRouter(prefix="/api/actions", tags=["actions"])

_AUG_2026 = DateRange(start=dt.date(2026, 8, 1), end_exclusive=dt.date(2026, 9, 1))


def _metric_value(
    runner: SqlMetricRunner, metric: str, *, campaign_id: str | None = None,
    reason_level_1: str | None = None,
) -> float | None:
    filters = []
    if campaign_id is not None:
        filters.append(Filter(dimension="campaign_id", op="eq", value=campaign_id))
    if reason_level_1 is not None:
        filters.append(Filter(dimension="reason_level_1", op="eq", value=reason_level_1))
    fact = runner.run(
        MetricRequest(metrics=(metric,), filters=tuple(filters), date_range=_AUG_2026),
        fact_id="Fx", title="kiem tra dieu kien hanh dong",
    )
    value = fact.rows[0][metric] if fact.rows else None
    return float(value) if value is not None else None


def _segment_n(segments_table: list[dict[str, Any]], segment_id: str) -> int:
    for s in segments_table:
        if s["segment_id"] == segment_id:
            return int(s["n"])
    return 0


def _check_reloan_campaign_dormant(
    runner: SqlMetricRunner, segments: list[dict[str, Any]]
) -> tuple[bool, str]:
    n = _segment_n(segments, "dormant")
    romi = _metric_value(runner, "romi", campaign_id="CMP-ZL-RL1")
    ok = n >= 100 and romi is not None and romi > 2.0
    return ok, f"dormant n={n} (can >=100), ROMI CMP-ZL-RL1={romi} (can >2.0)"


def _check_cut_broker_budget(runner: SqlMetricRunner) -> tuple[bool, str]:
    notes = []
    for campaign_id in ("CMP-PTN-BRK01", "CMP-PTN-MOMO"):
        romi = _metric_value(runner, "romi", campaign_id=campaign_id)
        share = _metric_value(runner, "partner_fee_share", campaign_id=campaign_id)
        notes.append(f"{campaign_id}: romi={romi}, partner_fee_share={share}")
        if romi is not None and share is not None and romi < 0 and share > 0.15:
            return True, "; ".join(notes)
    return False, "; ".join(notes)


def _check_tighten_tiktok(runner: SqlMetricRunner) -> tuple[bool, str]:
    campaign_id = "CMP-TT-001"
    rate = _metric_value(runner, "lead_to_application_rate", campaign_id=campaign_id)
    approval = _metric_value(runner, "approval_rate", campaign_id=campaign_id)
    ok = rate is not None and approval is not None and rate < 0.15 and approval < 0.50
    return ok, f"{campaign_id}: lead_to_application_rate={rate}, approval_rate={approval}"


def _check_push_app_adoption(segments: list[dict[str, Any]]) -> tuple[bool, str]:
    n = _segment_n(segments, "app_gap")
    return n >= 100, f"app_gap n={n} (can >=100)"


def _check_activate_never_applied(segments: list[dict[str, Any]]) -> tuple[bool, str]:
    n = _segment_n(segments, "never_activated")
    return n >= 100, f"never_activated n={n} (can >=100)"


def _check_reduce_cic_rejections(runner: SqlMetricRunner) -> tuple[bool, str]:
    n = _metric_value(runner, "rejected_loans", reason_level_1="No xau CIC")
    ok = n is not None and n >= 200
    return ok, f"rejected_loans[No xau CIC]={n} (can >=200)"


def _evaluate_eligibility(
    action: ActionSpec, runner: SqlMetricRunner, segments: list[dict[str, Any]]
) -> tuple[bool, str]:
    """Dispatch RO RANG theo tung action.id - tranh loi so luong tham so am
    tham khi cac ham kiem tra co chu ky khac nhau (mot so can `segments`,
    mot so can `runner`, mot so can ca hai)."""
    if action.id == "reloan_campaign_dormant":
        return _check_reloan_campaign_dormant(runner, segments)
    if action.id == "cut_broker_budget":
        return _check_cut_broker_budget(runner)
    if action.id == "tighten_tiktok_targeting":
        return _check_tighten_tiktok(runner)
    if action.id == "push_app_adoption":
        return _check_push_app_adoption(segments)
    if action.id == "activate_never_applied":
        return _check_activate_never_applied(segments)
    if action.id == "reduce_cic_rejections":
        return _check_reduce_cic_rejections(runner)
    return False, "chua co phep kiem tra dieu kien cho hanh dong nay"


def _impact_vnd(action: ActionSpec) -> float | None:
    """Lay so tien tac dong TRUC TIEP tu khoi `validated` da kiem chung -
    khong tinh lai qua `impact_formula` (xem # ASSUMPTION dau file)."""
    if not action.validated:
        return None
    v = action.validated
    if "impact_vnd" in v:
        return float(v["impact_vnd"])
    # Mot so hanh dong (cut_broker_budget) co validated theo tung campaign -
    # cong lai impact_vnd cua tat ca campaign da du dieu kien.
    nested_impacts = [
        entry["impact_vnd"] for entry in v.values()
        if isinstance(entry, dict) and "impact_vnd" in entry
    ]
    return float(sum(nested_impacts)) if nested_impacts else None


@router.get("")
def list_actions(
    runner: SqlMetricRunner = Depends(get_metric_runner),
) -> list[dict[str, Any]]:
    cfg = get_analytics_config()
    segments = build_segment_table()

    out: list[dict[str, Any]] = []
    for action in sorted(cfg.actions, key=lambda a: a.priority):
        eligible, note = _evaluate_eligibility(action, runner, segments)
        out.append({
            "id": action.id,
            "label_vi": action.label_vi,
            "target_segment": action.target_segment,
            "target_metric": action.target_metric,
            "effort": action.effort,
            "priority": action.priority,
            "requires_experiment": action.requires_experiment,
            "impact_caveat_vi": action.impact_caveat_vi,
            "eligible": eligible,
            "eligibility_note_vi": note,
            "impact_vnd": _impact_vnd(action),
            "validated": action.validated,
        })
    return out


__all__ = ["router"]
