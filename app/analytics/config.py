"""Nap `config/analytics.yaml` (protected - chi doc, xem CLAUDE.md).

NGOAI LE duy nhat cho quy tac "analytics/ khong I/O": day la doc file YAML cuc
bo, khong phai DB hay mang, giong cach `app/semantic/catalog.py` doc metrics.yml.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PATH = ROOT / "config" / "analytics.yaml"


@dataclass(frozen=True, slots=True)
class SegmentRuleSpec:
    id: str
    label_vi: str
    action_hint_vi: str


@dataclass(frozen=True, slots=True)
class PRepeatCell:
    """Mot o trong bang tra p_repeat. `x`/`n` la so THAT (dung cho wilson_ci),
    `p` la ty le da lam tron trong YAML - dung `x/n` khi can do chinh xac."""
    n: int
    x: int
    p: float
    ci95: tuple[float, float]
    usable: bool = True


@dataclass(frozen=True, slots=True)
class ActionSpec:
    id: str
    label_vi: str
    trigger: str
    target_metric: str
    impact_formula: str
    impact_caveat_vi: str
    effort: str
    priority: int
    target_segment: str | None = None
    requires_experiment: bool = False
    validated: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AnalyticsConfig:
    raw: dict[str, Any]

    # -- phan khuc --
    profit_high_percentile: float
    segment_rules: tuple[SegmentRuleSpec, ...]   # THU TU dung - quan trong

    # -- CLV --
    horizon_factor: float
    avg_profit_per_repeat_loan: float
    clv_min_sample_size: int
    p_repeat_by_income_and_app: dict[str, PRepeatCell]
    p_repeat_by_income: dict[str, PRepeatCell]
    p_repeat_global: PRepeatCell
    not_applicable_segments: tuple[str, ...]

    # -- hanh dong D3 --
    actions: tuple[ActionSpec, ...]

    # -- tham so thong ke chung --
    stats_alpha: float
    stats_min_effect_size: float
    stats_min_sample_size: int
    bootstrap_iterations: int
    bootstrap_seed: int

    @property
    def segment_rule_ids(self) -> tuple[str, ...]:
        return tuple(r.id for r in self.segment_rules)


def _cell(raw: dict[str, Any]) -> PRepeatCell:
    return PRepeatCell(
        n=int(raw["n"]), x=int(raw["x"]), p=float(raw["p"]),
        ci95=(float(raw["ci95"][0]), float(raw["ci95"][1])),
        usable=bool(raw.get("usable", True)),
    )


def _action(raw: dict[str, Any]) -> ActionSpec:
    return ActionSpec(
        id=raw["id"], label_vi=raw["label_vi"], trigger=raw["trigger"],
        target_metric=raw["target_metric"], impact_formula=raw["impact_formula"],
        impact_caveat_vi=raw["impact_caveat_vi"].strip(), effort=raw["effort"],
        priority=int(raw["priority"]), target_segment=raw.get("target_segment"),
        requires_experiment=bool(raw.get("requires_experiment", False)),
        validated=raw.get("validated"),
    )


def load_analytics_config(path: Path = DEFAULT_PATH) -> AnalyticsConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    seg = raw["segmentation"]
    clv = raw["clv"]
    stats = raw["stats"]
    p_repeat = clv["p_repeat_lookup"]

    return AnalyticsConfig(
        raw=raw,
        profit_high_percentile=float(seg["profit_high_percentile"]),
        segment_rules=tuple(
            SegmentRuleSpec(id=r["id"], label_vi=r["label_vi"],
                             action_hint_vi=r["action_hint_vi"].strip())
            for r in seg["rules"]
        ),
        horizon_factor=float(clv["horizon_factor"]),
        avg_profit_per_repeat_loan=float(clv["avg_profit_per_repeat_loan"]),
        clv_min_sample_size=int(clv["min_sample_size"]),
        p_repeat_by_income_and_app={
            k: _cell(v) for k, v in p_repeat["by_income_and_app"].items()
        },
        p_repeat_by_income={k: _cell(v) for k, v in p_repeat["by_income"].items()},
        p_repeat_global=_cell(p_repeat["global"]),
        not_applicable_segments=tuple(clv.get("not_applicable_segments", ())),
        actions=tuple(_action(a) for a in raw.get("actions", [])),
        stats_alpha=float(stats["alpha"]),
        stats_min_effect_size=float(stats["min_effect_size"]),
        stats_min_sample_size=int(stats["min_sample_size"]),
        bootstrap_iterations=int(stats["bootstrap_iterations"]),
        bootstrap_seed=int(stats["bootstrap_seed"]),
    )


@lru_cache(maxsize=1)
def get_analytics_config() -> AnalyticsConfig:
    return load_analytics_config()


__all__ = [
    "AnalyticsConfig", "SegmentRuleSpec", "PRepeatCell", "ActionSpec",
    "load_analytics_config", "get_analytics_config",
]
