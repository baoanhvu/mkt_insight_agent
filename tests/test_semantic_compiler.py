"""Kiem tra nam bat bien cua compiler (docs/05-semantic-layer.md muc 5.3) va
cac loi ngu nghia phai bi chan TRUOC KHI cham database - day la lop L0 cua
hang rao chong hallucination (R1/R2 trong CLAUDE.md).

Khong can Postgres - catalog va compiler la ham thuan.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.contracts import DateRange, Filter, MetricRequest
from app.errors import (
    DimensionNotAllowedError,
    ForbiddenMetricError,
    InsufficientHistoryError,
    InvalidFilterError,
    UnknownDimensionError,
    UnknownMetricError,
)
from app.semantic.catalog import load_catalog
from app.semantic.compiler import MetricCompiler

AUG_2026 = DateRange(start=dt.date(2026, 8, 1), end_exclusive=dt.date(2026, 9, 1))


@pytest.fixture(scope="module")
def compiler() -> MetricCompiler:
    return MetricCompiler(load_catalog())


# =============================================================================
# Bat bien 1 - ten bang/cot CHI lay tu catalog
# =============================================================================

def test_unknown_metric_is_rejected(compiler: MetricCompiler) -> None:
    with pytest.raises(UnknownMetricError):
        compiler.compile(MetricRequest(metrics=("chi_so_bia_ra_khong_ton_tai",)))


def test_unknown_dimension_is_rejected(compiler: MetricCompiler) -> None:
    with pytest.raises(UnknownDimensionError):
        compiler.compile(
            MetricRequest(metrics=("romi",), dimensions=("dimension_bia_ra",))
        )


def test_generated_sql_never_contains_raw_metric_or_dimension_name_as_identifier_typo() -> None:
    """Ten cot trong SQL sinh ra PHAI khop dung cot trong catalog, khong phai
    ten nguoi dung go (o day trung nhau vi ten metric == ten cot, nhung dat
    test rieng de tuong lai khong ai vo tinh doi compiler sang string-format
    truc tiep tu MetricRequest.dimensions/metrics)."""
    catalog = load_catalog()
    compiler = MetricCompiler(catalog)
    cq = compiler.compile(MetricRequest(metrics=("romi",), dimensions=("campaign_id",)))
    dim = catalog.dimension("campaign_id", "application")
    assert dim.column in cq.sql
    assert "romi" in cq.sql


# =============================================================================
# Bat bien 2 - gia tri filter LUON di qua bind parameter
# =============================================================================

def test_filter_value_is_bound_not_concatenated(compiler: MetricCompiler) -> None:
    cq = compiler.compile(
        MetricRequest(
            metrics=("romi",),
            filters=(Filter(dimension="campaign_id", op="eq", value="CMP-ZL-RL1"),),
        )
    )
    assert "CMP-ZL-RL1" not in cq.sql  # gia tri KHONG duoc noi vao chuoi SQL
    assert ":f0" in cq.sql
    assert cq.params["f0"] == "CMP-ZL-RL1"


def test_sql_injection_attempt_in_filter_value_is_just_a_bound_string(
    compiler: MetricCompiler,
) -> None:
    """Gia tri filter la "chuoi bat ky" nguoi dung go vao - du no trong giong
    SQL injection thi van chi la MOT GIA TRI BOUND PARAM, khong bao gio duoc
    thuc thi nhu ma. Vi campaign_id co allowed_values, gia tri bia se bi chan
    o buoc validate truoc ca khi toi bind param - do cung la mot lop bao ve."""
    with pytest.raises(InvalidFilterError):
        compiler.compile(
            MetricRequest(
                metrics=("romi",),
                filters=(
                    Filter(dimension="campaign_id", op="eq", value="x'; DROP TABLE mart.mart_application; --"),
                ),
            )
        )


def test_in_filter_expands_to_one_param_per_value(compiler: MetricCompiler) -> None:
    cq = compiler.compile(
        MetricRequest(
            metrics=("romi",),
            filters=(
                Filter(dimension="campaign_id", op="in", value=["CMP-ZL-RL1", "CMP-GG-001"]),
            ),
        )
    )
    assert cq.params["f0_0"] == "CMP-ZL-RL1"
    assert cq.params["f0_1"] == "CMP-GG-001"
    assert "IN (:f0_0, :f0_1)" in cq.sql


# =============================================================================
# Bat bien 3 - LUON co LIMIT
# =============================================================================

def test_always_has_limit(compiler: MetricCompiler) -> None:
    cq = compiler.compile(MetricRequest(metrics=("romi",)))
    assert "LIMIT" in cq.sql


def test_limit_is_capped_by_catalog_max_rows(compiler: MetricCompiler) -> None:
    catalog = load_catalog()
    cq = compiler.compile(MetricRequest(metrics=("romi",), limit=10**9))
    assert f"LIMIT {catalog.max_rows}" in cq.sql


# =============================================================================
# Bat bien 4 - LUON them COUNT(*) AS _n_rows
# =============================================================================

def test_always_selects_n_rows(compiler: MetricCompiler) -> None:
    cq = compiler.compile(MetricRequest(metrics=("romi",)))
    assert "AS _n_rows" in cq.sql


# =============================================================================
# Bat bien 5 - ORDER BY chi nhan ten da co trong SELECT
# =============================================================================

def test_order_by_must_be_a_selected_name(compiler: MetricCompiler) -> None:
    with pytest.raises(InvalidFilterError):
        compiler.compile(MetricRequest(metrics=("romi",), order_by="cot_khong_ton_tai"))


def test_order_by_selected_metric_works(compiler: MetricCompiler) -> None:
    cq = compiler.compile(MetricRequest(metrics=("romi",), order_by="romi"))
    assert "ORDER BY romi DESC" in cq.sql


# =============================================================================
# Cac hang rao ngu nghia khac (R1: LLM khong tu tinh so, o day la khong tu
# CHON duoc chi so/dimension khong hop le)
# =============================================================================

def test_forbidden_metric_is_rejected_with_reason(compiler: MetricCompiler) -> None:
    with pytest.raises(ForbiddenMetricError, match="31 ngay"):
        compiler.compile(MetricRequest(metrics=("month_over_month_growth",)))


def test_computed_by_metric_cannot_be_sql_compiled(compiler: MetricCompiler) -> None:
    with pytest.raises(ForbiddenMetricError):
        compiler.compile(MetricRequest(metrics=("clv_predicted",)))


def test_dimension_not_in_metric_allowed_list_is_rejected(compiler: MetricCompiler) -> None:
    """`segment_size_share` chi cho phep dimension [segment]; `occupation` cung
    thuoc dataset `segment` (nen khong bi UnknownDimensionError) nhung khong
    nam trong allowed_dimensions cua chinh metric nay."""
    with pytest.raises(DimensionNotAllowedError):
        compiler.compile(
            MetricRequest(metrics=("segment_size_share",), dimensions=("occupation",))
        )


def test_mixing_metrics_from_different_datasets_is_rejected(compiler: MetricCompiler) -> None:
    """`romi` o dataset application, `customers` o dataset customer - khong
    gop duoc trong mot cau SELECT/GROUP BY."""
    with pytest.raises(InvalidFilterError):
        compiler.compile(MetricRequest(metrics=("romi", "customers")))


def test_date_range_outside_transactional_window_raises_insufficient_history(
    compiler: MetricCompiler,
) -> None:
    """DQ-03: du lieu giao dich chi co 01/08-31/08/2026."""
    with pytest.raises(InsufficientHistoryError):
        compiler.compile(
            MetricRequest(
                metrics=("romi",),
                date_range=DateRange(
                    start=dt.date(2026, 1, 1), end_exclusive=dt.date(2026, 2, 1)
                ),
            )
        )


def test_date_range_within_window_is_accepted(compiler: MetricCompiler) -> None:
    cq = compiler.compile(MetricRequest(metrics=("romi",), date_range=AUG_2026))
    assert ":d_from" in cq.sql and ":d_to" in cq.sql


def test_having_only_accepts_selected_name_and_number(compiler: MetricCompiler) -> None:
    cq = compiler.compile(MetricRequest(metrics=("romi",), having="_n_rows >= 30"))
    assert "HAVING _n_rows >= :having_value" in cq.sql
    assert cq.params["having_value"] == 30.0


def test_having_rejects_free_form_sql(compiler: MetricCompiler) -> None:
    with pytest.raises(InvalidFilterError):
        compiler.compile(
            MetricRequest(metrics=("romi",), having="1=1; DROP TABLE mart.mart_application")
        )


def test_metric_caveat_is_propagated_to_compiled_query(compiler: MetricCompiler) -> None:
    """lead_to_application_rate PHAI mang theo caveat ve khong co attribution
    tung lead - Narrator bat buoc nhac lai (08 muc 3)."""
    cq = compiler.compile(MetricRequest(metrics=("lead_to_application_rate",)))
    assert any("attribution" in c for c in cq.caveats)
