"""Thong ke thuan: wilson_ci, two_proportion_ztest, bootstrap_mean_diff,
cohens_d, anova_oneway. Xem docs/11-module-spec.md muc 11.4.

`seed` CO DINH (mac dinh 42, khop config/analytics.yaml -> stats.bootstrap_seed)
de cung mot cau hoi luon cho cung p-value - xem CLAUDE.md va docs/13-testing-eval.md.

QUY TAC: module nay KHONG doc `config/analytics.yaml` (khac `config.py`). Moi
tham so (alpha, min_effect_size, min_sample_size) deu la ARGUMENT, khong phai
gia tri an trong module - nho vay ham o day test duoc voi bat ky tham so nao
ma khong can nap file.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats as sp_stats

from app.contracts import Comparison

# ASSUMPTION: hai cau nay la KET LUAN THONG KE gan chat voi gia tri `significant`
# do chinh code tinh ra (khong phai van phong tuy chinh nguoi dung sua duoc qua
# YAML) - xem tranh luan trong docs/06 muc 6.5 va R5 o CLAUDE.md. Neu sau nay
# can doi giong van, chuyen vao prompts/*.yaml (T07) va de Narrator dien dat
# lai; verdict_vi o day chi la nhan noi bo cho Comparison, khong phai cau van
# cuoi cung nguoi dung doc.
_VERDICT_SIGNIFICANT = "Khác biệt có ý nghĩa thống kê."
_VERDICT_NOT_SIGNIFICANT = "Khác biệt nằm trong sai số thống kê, không đủ để kết luận."


def wilson_ci(successes: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Khoang tin cay Wilson cho mot ty le. Dung Wilson chu khong dung Wald vi
    Wald sai nang khi n nho hoac p gan 0/1 - ca hai truong hop deu xuat hien
    trong bo du lieu nay (xem config/analytics.yaml -> clv.p_repeat_lookup,
    nhom ">=20M" co n=17/24)."""
    if n <= 0:
        raise ValueError(f"n phai > 0, nhan {n}")
    if not (0 <= successes <= n):
        raise ValueError(f"successes phai trong [0, {n}], nhan {successes}")

    z = float(sp_stats.norm.ppf(1 - (1 - conf) / 2))
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def two_proportion_ztest(
    x1: int, n1: int, x2: int, n2: int, *,
    alpha: float = 0.05, min_effect_size: float = 0.2, min_sample_size: int = 30,
    left_ref: str = "", right_ref: str = "", metric: str = "",
) -> Comparison:
    """Kiem dinh z hai ty le doc lap. `effect_size` la Cohen's h (chuan cho so
    sanh hai ty le, on dinh hon chenh lech thuan tuy khi p gan 0 hoac 1)."""
    if n1 <= 0 or n2 <= 0:
        raise ValueError("n1 va n2 phai > 0")

    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se > 0 else 0.0
    p_value = float(2 * (1 - sp_stats.norm.cdf(abs(z))))

    z_crit = float(sp_stats.norm.ppf(1 - alpha / 2))
    se_diff = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p1 - p2
    ci = (diff - z_crit * se_diff, diff + z_crit * se_diff)

    effect_size = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))

    significant = (
        p_value < alpha
        and abs(effect_size) >= min_effect_size
        and min(n1, n2) >= min_sample_size
    )

    return Comparison(
        left=left_ref, right=right_ref, metric=metric, diff=diff, p_value=p_value,
        ci=ci, effect_size=effect_size, n_left=n1, n_right=n2, significant=significant,
        verdict_vi=_VERDICT_SIGNIFICANT if significant else _VERDICT_NOT_SIGNIFICANT,
        test_name="two_proportion_ztest",
    )


def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d voi do lech chuan gop (pooled). Duong = a lon hon b."""
    arr_a, arr_b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n1, n2 = len(arr_a), len(arr_b)
    if n1 < 2 or n2 < 2:
        raise ValueError("moi nhom can it nhat 2 quan sat de tinh do lech chuan")
    var1, var2 = arr_a.var(ddof=1), arr_b.var(ddof=1)
    pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
    pooled_sd = math.sqrt(pooled_var)
    if pooled_sd == 0:
        return 0.0
    return float((arr_a.mean() - arr_b.mean()) / pooled_sd)


def bootstrap_mean_diff(
    a: Sequence[float], b: Sequence[float], *, n_boot: int = 2000, seed: int = 42,
    alpha: float = 0.05, min_effect_size: float = 0.2, min_sample_size: int = 30,
    left_ref: str = "", right_ref: str = "", metric: str = "",
) -> Comparison:
    """So sanh trung binh hai nhom bang bootstrap thay vi t-test, vi phan bo
    loi nhuan lech manh (sigma ca the ~738k tren trung binh ~200k - t-test gia
    dinh phan bo gan chuan se cho khoang tin cay sai). `seed` CO DINH: cung du
    lieu dau vao luon cho cung ket qua, khong phu thuoc lan chay."""
    arr_a, arr_b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n1, n2 = len(arr_a), len(arr_b)
    if n1 == 0 or n2 == 0:
        raise ValueError("ca hai nhom phai co it nhat mot quan sat")

    observed_diff = float(arr_a.mean() - arr_b.mean())

    rng = np.random.default_rng(seed)
    boot_diffs = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        sample_a = rng.choice(arr_a, size=n1, replace=True)
        sample_b = rng.choice(arr_b, size=n2, replace=True)
        boot_diffs[i] = sample_a.mean() - sample_b.mean()

    lo, hi = float(np.percentile(boot_diffs, 2.5)), float(np.percentile(boot_diffs, 97.5))

    # p-value xap xi hai phia: ty le phan bo bootstrap vuot qua 0 theo huong
    # nguoc voi dau cua diff quan sat, nhan 2 (chuan hai phia), gioi han o 1.0.
    if observed_diff >= 0:
        one_sided = float(np.mean(boot_diffs <= 0))
    else:
        one_sided = float(np.mean(boot_diffs >= 0))
    p_value = min(1.0, 2 * one_sided)

    effect_size = cohens_d(a, b) if n1 >= 2 and n2 >= 2 else 0.0
    significant = (
        not (lo <= 0 <= hi)
        and abs(effect_size) >= min_effect_size
        and min(n1, n2) >= min_sample_size
        and p_value < alpha
    )

    return Comparison(
        left=left_ref, right=right_ref, metric=metric, diff=observed_diff,
        p_value=p_value, ci=(lo, hi), effect_size=effect_size, n_left=n1, n_right=n2,
        significant=significant,
        verdict_vi=_VERDICT_SIGNIFICANT if significant else _VERDICT_NOT_SIGNIFICANT,
        test_name="bootstrap_mean_diff",
    )


class AnovaResult:
    """Ket qua ANOVA mot chieu tren N nhom (N > 2, nen khong khop khuon
    `Comparison` - kieu do la SO SANH HAI NHOM)."""

    __slots__ = ("f_stat", "p_value", "significant", "n_groups", "n_total")

    def __init__(self, f_stat: float, p_value: float, significant: bool,
                 n_groups: int, n_total: int) -> None:
        self.f_stat = f_stat
        self.p_value = p_value
        self.significant = significant
        self.n_groups = n_groups
        self.n_total = n_total

    def __repr__(self) -> str:  # pragma: no cover - chi phuc vu debug
        return (f"AnovaResult(f_stat={self.f_stat:.4f}, p_value={self.p_value:.4f}, "
                f"significant={self.significant}, n_groups={self.n_groups})")


def anova_oneway(groups: Sequence[Sequence[float]], *, alpha: float = 0.05) -> AnovaResult:
    """ANOVA mot chieu tren >= 2 nhom (dung de kiem tra occupation KHONG phan
    hoa gia tri khach hang - xem config/analytics.yaml -> descriptive_only_dimensions)."""
    if len(groups) < 2:
        raise ValueError("ANOVA can it nhat hai nhom")
    arrays = [np.asarray(g, dtype=float) for g in groups]
    f_stat, p_value = sp_stats.f_oneway(*arrays)
    return AnovaResult(
        f_stat=float(f_stat), p_value=float(p_value), significant=bool(p_value < alpha),
        n_groups=len(arrays), n_total=sum(len(a) for a in arrays),
    )


__all__ = [
    "wilson_ci", "two_proportion_ztest", "cohens_d", "bootstrap_mean_diff",
    "anova_oneway", "AnovaResult",
]
