"""`stats_tool` - BAT BUOC goi truoc moi phat bieu so sanh (docs/06-agent-design.md
muc 6.4). Boc mong quanh `app.analytics.stats` de gan dia chi Cell (`left`/
`right`) vao ket qua `Comparison`, phuc vu lop L4 (stats_guard, T09) doi
chieu cau van voi ket qua kiem dinh.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.analytics.config import AnalyticsConfig, get_analytics_config
from app.analytics.stats import (
    AnovaResult,
    bootstrap_mean_diff,
    cohens_d,
    two_proportion_ztest,
    wilson_ci,
)
from app.contracts import Comparison


class StatsTool:
    def __init__(self, cfg: AnalyticsConfig | None = None) -> None:
        self.cfg = cfg or get_analytics_config()

    def wilson_ci(self, successes: int, n: int, conf: float = 0.95) -> tuple[float, float]:
        return wilson_ci(successes, n, conf=conf)

    def compare_proportions(
        self, x1: int, n1: int, x2: int, n2: int, *,
        left_ref: str = "", right_ref: str = "", metric: str = "",
    ) -> Comparison:
        return two_proportion_ztest(
            x1, n1, x2, n2, alpha=self.cfg.stats_alpha,
            min_effect_size=self.cfg.stats_min_effect_size,
            min_sample_size=self.cfg.stats_min_sample_size,
            left_ref=left_ref, right_ref=right_ref, metric=metric,
        )

    def compare_means(
        self, a: Sequence[float], b: Sequence[float], *,
        left_ref: str = "", right_ref: str = "", metric: str = "",
    ) -> Comparison:
        return bootstrap_mean_diff(
            a, b, n_boot=self.cfg.bootstrap_iterations, seed=self.cfg.bootstrap_seed,
            alpha=self.cfg.stats_alpha, min_effect_size=self.cfg.stats_min_effect_size,
            min_sample_size=self.cfg.stats_min_sample_size,
            left_ref=left_ref, right_ref=right_ref, metric=metric,
        )

    def cohens_d(self, a: Sequence[float], b: Sequence[float]) -> float:
        return cohens_d(a, b)

    def anova(self, groups: Sequence[Sequence[float]]) -> AnovaResult:
        from app.analytics.stats import anova_oneway

        return anova_oneway(groups, alpha=self.cfg.stats_alpha)


__all__ = ["StatsTool"]
