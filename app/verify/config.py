"""Nap `config/verify.yaml` (protected - chi doc). Xem docs/08-anti-hallucination.md."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PATH = ROOT / "config" / "verify.yaml"


@dataclass(frozen=True, slots=True)
class NumericPolicySpec:
    mode: str
    decimals: int = 2
    tol: float = 0.0
    alias: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerifyConfig:
    raw: dict[str, Any]

    # L2
    require_grounding_rate: float
    numeric_policies: dict[str, NumericPolicySpec]
    unit_aliases: dict[str, float]
    allowlist_years: tuple[int, int]
    allowlist_ordinals: tuple[int, int]
    allowlist_literals: tuple[float, ...]
    id_patterns: tuple[str, ...]

    # L3
    entity_fuzzy_threshold: float

    # L4
    stats_alpha: float
    stats_min_effect_size: float
    stats_min_sample_size: int
    comparative_markers_vi: tuple[str, ...]
    causal_markers_vi: tuple[str, ...]
    correlation_phrases_vi: tuple[str, ...]

    # L6
    t_high: float
    t_low: float
    trust_weights: dict[str, float]


def load_verify_config(path: Path = DEFAULT_PATH) -> VerifyConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    numeric = raw["numeric"]
    entity = raw["entity"]
    stats = raw["stats_guard"]
    trust = raw["trust"]

    policies = {
        name: NumericPolicySpec(
            mode=spec["mode"], decimals=int(spec.get("decimals", 2)),
            tol=float(spec.get("tol", 0.0)), alias=tuple(spec.get("alias", ())),
        )
        for name, spec in numeric["policy"].items()
    }

    return VerifyConfig(
        raw=raw,
        require_grounding_rate=float(numeric["require_grounding_rate"]),
        numeric_policies=policies,
        unit_aliases={k: float(v) for k, v in numeric.get("unit_aliases", {}).items()},
        allowlist_years=(
            int(numeric["allowlist"]["years"]["min"]), int(numeric["allowlist"]["years"]["max"]),
        ),
        allowlist_ordinals=(
            int(numeric["allowlist"]["ordinals"]["min"]), int(numeric["allowlist"]["ordinals"]["max"]),
        ),
        allowlist_literals=tuple(float(v) for v in numeric["allowlist"]["literals"]),
        id_patterns=tuple(numeric["allowlist"]["id_patterns"]),
        entity_fuzzy_threshold=float(entity["fuzzy_threshold"]),
        stats_alpha=float(stats["alpha"]),
        stats_min_effect_size=float(stats["min_effect_size"]),
        stats_min_sample_size=int(stats["min_sample_size"]),
        comparative_markers_vi=tuple(stats["comparative_markers_vi"]),
        causal_markers_vi=tuple(stats["causal_markers_vi"]),
        correlation_phrases_vi=tuple(stats["correlation_phrases_vi"]),
        t_high=float(trust["t_high"]),
        t_low=float(trust["t_low"]),
        trust_weights={k: float(v) for k, v in trust["weights"].items()},
    )


@lru_cache(maxsize=1)
def get_verify_config() -> VerifyConfig:
    return load_verify_config()


__all__ = ["VerifyConfig", "NumericPolicySpec", "load_verify_config", "get_verify_config"]
