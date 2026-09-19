"""Khang dinh cac gia tri `reference` trong config/semantic/metrics.yml van
dung tren du lieu THAT (khong phai DuckDB mirror - Postgres cua profile test,
da nap boi etl/ o T02). Day la test hop dong: doi dinh nghia chi so ma quen
cap nhat reference thi test nay do (docs/05-semantic-layer.md muc 5.7).

BAT BUOC (docs/17-implementation-guide.md T03): khang dinh dung 6 gia tri
ROMI tham chieu trong CLAUDE.md. Test nay doc `reference` truc tiep tu
metrics.yml - KHONG go tay so lieu - de neu ai sua file .yml (chi cach hop le
de doi mot chi so) ma quen cap nhat `reference` thi CI do ngay.

Yeu cau: `docker compose -f docker-compose.dev.yml up -d` + da chay
`python -m etl.load_excel && python -m etl.build_marts` (T02) truoc do.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.contracts import DateRange, Filter, MetricRequest
from app.semantic.catalog import YamlCatalog, load_catalog
from app.semantic.compiler import MetricCompiler
from app.settings import get_settings

AUG_2026 = DateRange(start=dt.date(2026, 8, 1), end_exclusive=dt.date(2026, 9, 1))


@pytest.fixture(scope="module")
def catalog() -> YamlCatalog:
    return load_catalog()


@pytest.fixture(scope="module")
def compiler(catalog: YamlCatalog) -> MetricCompiler:
    return MetricCompiler(catalog)


@pytest.fixture(scope="module")
def pg_engine() -> Engine:
    settings = get_settings()
    engine = create_engine(settings.database.url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.skip(
            f"Postgres test khong san sang ({exc}) - chay "
            "'docker compose -f docker-compose.dev.yml up -d' va "
            "'python -m etl.load_excel && python -m etl.build_marts' truoc."
        )
    return engine


def _run(
    compiler: MetricCompiler,
    engine: Engine,
    metrics: tuple[str, ...],
    dimensions: tuple[str, ...] = (),
    filters: tuple[Filter, ...] = (),
    date_range: DateRange | None = None,
) -> list[dict[str, Any]]:
    cq = compiler.compile(
        MetricRequest(metrics=metrics, dimensions=dimensions, filters=filters,
                      date_range=date_range, limit=1000)
    )
    with engine.connect() as conn:
        rows = conn.execute(text(cq.sql), cq.params).mappings().all()
    return [dict(r) for r in rows]


# =============================================================================
# BAT BUOC: 6 gia tri ROMI tham chieu (CLAUDE.md, doc truc tiep tu metrics.yml)
# =============================================================================

def _romi_reference() -> dict[str, float]:
    catalog = load_catalog()
    ref = catalog.metric("romi").reference
    assert ref is not None, "metrics.yml: romi phai co khoi 'reference'"
    return dict(ref["by_campaign"])


@pytest.mark.parametrize("campaign_id,expected_romi", sorted(_romi_reference().items()))
def test_romi_matches_reference(
    compiler: MetricCompiler, pg_engine: Engine, campaign_id: str, expected_romi: float
) -> None:
    rows = _run(
        compiler, pg_engine, ("romi",),
        filters=(Filter(dimension="campaign_id", op="eq", value=campaign_id),),
        date_range=AUG_2026,
    )
    assert len(rows) == 1
    assert float(rows[0]["romi"]) == pytest.approx(expected_romi, abs=1e-4)


def test_romi_display_values_match_claude_md_pinned_table(
    compiler: MetricCompiler, pg_engine: Engine
) -> None:
    """Sau parse_vi_number nguoc, day la 6 gia tri hien thi (format "0.00")
    dung trong bang o CLAUDE.md - kiem tra rieng vi day la "sau giai lam
    tron", khac voi gia tri chinh xac o test tren."""
    rows = _run(compiler, pg_engine, ("romi", "net_profit"), dimensions=("campaign_id",),
                date_range=AUG_2026)
    by_id = {r["campaign_id"]: r for r in rows}

    expected = {
        "CMP-ZL-RL1": (6.20, 392_498_488),
        "CMP-GG-001": (1.60, 88_164_340),
        "CMP-FB-001": (1.31, 77_767_299),
        "CMP-TT-001": (0.67, 35_746_732),
        "CMP-PTN-MOMO": (-0.41, -17_529_775),
        "CMP-PTN-BRK01": (-1.85, -66_794_874),
    }
    for campaign_id, (romi_display, net_profit) in expected.items():
        row = by_id[campaign_id]
        assert round(float(row["romi"]), 2) == romi_display
        assert round(float(row["net_profit"])) == net_profit


# =============================================================================
# Doi chieu mo rong: cac metric khac co reference["total"], tren ca 4 dataset
# =============================================================================

@pytest.mark.parametrize(
    "metric_name,date_range",
    [
        ("applications", AUG_2026),
        ("disbursed_loans", AUG_2026),
        ("rejected_loans", AUG_2026),
        ("net_profit", AUG_2026),
        ("customers", None),          # dataset customer: snapshot, khong loc theo ngay
        ("clv_to_date", None),
        ("never_applied_customers", None),   # dataset segment
        ("dormant_customers", None),
    ],
)
def test_metric_total_matches_reference(
    compiler: MetricCompiler, pg_engine: Engine, metric_name: str, date_range: DateRange | None
) -> None:
    catalog = load_catalog()
    expected = catalog.metric(metric_name).reference["total"]
    rows = _run(compiler, pg_engine, (metric_name,), date_range=date_range)
    assert len(rows) == 1
    got = rows[0][metric_name]
    if isinstance(expected, float):
        assert float(got) == pytest.approx(expected, rel=1e-3)
    else:
        assert round(float(got)) == expected


def test_clv_to_date_matches_net_profit_total_cross_dataset_sanity_check(
    compiler: MetricCompiler, pg_engine: Engine
) -> None:
    """clv_to_date (dataset customer) = SUM(profit_to_date) va net_profit
    (dataset application) = SUM(net_profit) phai KHOP nhau - hai bang khac
    nhau cung dem tong loi nhuan, day la phep doi chieu cheo tot nhat co the."""
    net_profit = _run(compiler, pg_engine, ("net_profit",), date_range=AUG_2026)[0]["net_profit"]
    clv = _run(compiler, pg_engine, ("clv_to_date",))[0]["clv_to_date"]
    assert float(net_profit) == pytest.approx(float(clv), rel=1e-6)


def test_approval_rate_matches_reference_per_campaign(
    compiler: MetricCompiler, pg_engine: Engine
) -> None:
    catalog = load_catalog()
    ref = dict(catalog.metric("approval_rate").reference["by_campaign"])
    rows = _run(compiler, pg_engine, ("approval_rate",), dimensions=("campaign_id",),
                date_range=AUG_2026)
    by_id = {r["campaign_id"]: float(r["approval_rate"]) for r in rows}
    for campaign_id, expected in ref.items():
        assert by_id[campaign_id] == pytest.approx(expected, abs=1e-2)
