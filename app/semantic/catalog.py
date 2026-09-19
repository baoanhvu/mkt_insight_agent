"""Nap va tra cuu `config/semantic/metrics.yml` + `entities.yml`.

Day la NGUON SU THAT DUY NHAT ve y nghia du lieu (docs/05-semantic-layer.md
muc 5.1). LLM khong bao gio nhin thay schema DB tho - chi nhin file nay qua
`schema_tool`. Hai file .yml la protected (CLAUDE.md) - module nay chi DOC,
khong sinh hay suy dien them dinh nghia.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.contracts import Dataset, Dimension, Metric
from app.errors import (
    CatalogValidationError,
    ForbiddenMetricError,
    InsufficientHistoryError,
    UnknownDimensionError,
    UnknownMetricError,
)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ENTITIES_PATH = ROOT / "config" / "semantic" / "entities.yml"
DEFAULT_METRICS_PATH = ROOT / "config" / "semantic" / "metrics.yml"


@dataclass(frozen=True, slots=True)
class ForbiddenMetricSpec:
    metric_id: str
    reason_vi: str


@dataclass(frozen=True, slots=True)
class DataWindow:
    """Khoang thoi gian THAT co du lieu giao dich. Yeu cau nam ngoai day phai
    tra INSUFFICIENT_HISTORY, khong tra bang rong (DQ-03)."""
    date_from: _dt.date
    date_to_inclusive: _dt.date
    message_vi: str

    @property
    def end_exclusive(self) -> _dt.date:
        return self.date_to_inclusive + _dt.timedelta(days=1)

    def contains(self, start: _dt.date, end_exclusive: _dt.date) -> bool:
        return start >= self.date_from and end_exclusive <= self.end_exclusive


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise CatalogValidationError(f"file khong phai mapping YAML: {path}", path=str(path))
    return data


def _build_dataset(name: str, raw: dict[str, Any]) -> Dataset:
    return Dataset(
        name=name,
        table=raw["table"],
        grain=raw.get("grain", ""),
        default_date_column=raw.get("default_date_column", ""),
        description_vi=raw.get("description_vi", ""),
        caveat_vi=raw.get("caveat_vi"),
        row_count_expected=raw.get("row_count_expected"),
    )


def _build_dimension(name: str, raw: dict[str, Any]) -> Dimension:
    allowed = raw.get("allowed_values")
    ordered = raw.get("ordered")
    return Dimension(
        name=name,
        column=raw["column"],
        label_vi=raw.get("label_vi", name),
        datasets=tuple(raw.get("datasets", ())),
        type=raw.get("type", "text"),
        label_column=raw.get("label_column"),
        allowed_values=tuple(str(v) for v in allowed) if allowed else None,
        ordered=tuple(str(v) for v in ordered) if ordered else None,
        caveat_vi=raw.get("caveat_vi"),
        note_vi=raw.get("note_vi"),
    )


def _build_metric(name: str, raw: dict[str, Any]) -> Metric:
    # ASSUMPTION: cac chi so `computed_by` (vi du clv_predicted) khong khai
    # bao `dataset` trong metrics.yml vi chung khong chay qua SQL compiler -
    # dung "" lam sentinel "khong ap dung", xu ly rieng o dataset_of().
    return Metric(
        name=name,
        label_vi=raw.get("label_vi", name),
        dataset=raw.get("dataset", ""),
        unit=raw.get("unit", "text"),
        format=raw.get("format", ""),
        sql=raw.get("sql"),
        computed_by=raw.get("computed_by"),
        description_vi=raw.get("description_vi", ""),
        higher_is_better=raw.get("higher_is_better"),
        min_sample_size=raw.get("min_sample_size"),
        caveat_vi=raw.get("caveat_vi"),
        thresholds=raw.get("thresholds"),
        allowed_dimensions=tuple(raw.get("allowed_dimensions", ())),
        requires_confidence_interval=bool(raw.get("requires_confidence_interval", False)),
        requires_assumptions=bool(raw.get("requires_assumptions", False)),
        must_report_with=tuple(raw.get("must_report_with", ())),
        reference=raw.get("reference"),
    )


class YamlCatalog:
    """Trien khai `app.contracts.Catalog` (Protocol) tu hai file YAML.

    Cau truc khong doi sau khi nap - an toan dung chung giua nhieu request
    (khong co state thay doi).
    """

    def __init__(
        self,
        version: str,
        datasets: dict[str, Dataset],
        dimensions: dict[str, Dimension],
        metrics: dict[str, Metric],
        forbidden_metrics: dict[str, str],
        data_window: DataWindow | None,
        max_rows: int,
        default_limit: int,
    ) -> None:
        self.version = version
        self._datasets = datasets
        self._dimensions = dimensions
        self._metrics = metrics
        self._forbidden_metrics = forbidden_metrics
        self.data_window = data_window
        self.max_rows = max_rows
        self.default_limit = default_limit

    # -- Catalog Protocol -----------------------------------------------

    def metric(self, name: str) -> Metric:
        if name in self._forbidden_metrics:
            raise ForbiddenMetricError(
                self._forbidden_metrics[name], metric=name,
            )
        try:
            return self._metrics[name]
        except KeyError:
            raise UnknownMetricError(
                f"chi so khong ton tai trong catalog: '{name}'", metric=name
            ) from None

    def dimension(self, name: str, dataset: str) -> Dimension:
        try:
            dim = self._dimensions[name]
        except KeyError:
            raise UnknownDimensionError(
                f"dimension khong ton tai trong catalog: '{name}'", dimension=name
            ) from None
        if dataset and dataset not in dim.datasets:
            raise UnknownDimensionError(
                f"dimension '{name}' khong thuoc dataset '{dataset}' "
                f"(chi thuoc {dim.datasets})",
                dimension=name, dataset=dataset,
            )
        return dim

    def dataset(self, name: str) -> Dataset:
        try:
            return self._datasets[name]
        except KeyError:
            raise CatalogValidationError(
                f"dataset khong ton tai trong catalog: '{name}'", dataset=name
            ) from None

    def dataset_of(self, metric_name: str) -> Dataset:
        m = self.metric(metric_name)
        if m.computed_by is not None:
            raise ForbiddenMetricError(
                f"chi so '{metric_name}' duoc tinh boi Python ({m.computed_by}), "
                "khong co dataset SQL de compiler dung - goi qua MetricRunner, "
                "khong qua QueryCompiler",
                metric=metric_name,
            )
        return self.dataset(m.dataset)

    def all_dimension_values(self) -> set[str]:
        out: set[str] = set()
        for dim in self._dimensions.values():
            if dim.allowed_values:
                out.update(dim.allowed_values)
        return out

    def validate_against_db(self, engine: Any) -> list[str]:
        """Doi chieu moi `table`/`column` da khai bao voi schema THAT.

        `engine` la bat ky doi tuong co `.cursor()` kieu psycopg (duck-typed,
        vi Protocol khai bao `Any` - xem app/contracts.py). Tra ve danh sach
        loi (rong = catalog khop DB).
        """
        errors: list[str] = []
        cur = engine.cursor()
        for ds in self._datasets.values():
            schema, _, table = ds.table.partition(".")
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (schema, table),
            )
            real_columns = {row[0] for row in cur.fetchall()}
            if not real_columns:
                errors.append(f"dataset '{ds.name}': bang '{ds.table}' khong ton tai")
                continue
            for dim in self._dimensions.values():
                if ds.name not in dim.datasets:
                    continue
                base_col = dim.column.split("::")[0].strip()
                if base_col not in real_columns:
                    errors.append(
                        f"dimension '{dim.name}': cot '{base_col}' khong co trong "
                        f"'{ds.table}'"
                    )
        return errors

    # -- Tien ich rieng cua YamlCatalog (ngoai Protocol) -----------------

    def is_forbidden(self, metric_name: str) -> str | None:
        """None neu khong bi cam; nguoc lai tra ly do tieng Viet."""
        return self._forbidden_metrics.get(metric_name)

    def check_data_window(self, start: _dt.date, end_exclusive: _dt.date) -> None:
        """Raise InsufficientHistoryError neu khoang thoi gian vuot ngoai
        du lieu giao dich thuc te (DQ-03: chi co 01/08-31/08/2026)."""
        if self.data_window is None:
            return
        if not self.data_window.contains(start, end_exclusive):
            raise InsufficientHistoryError(
                self.data_window.message_vi,
                requested=f"{start}..{end_exclusive}",
                available=f"{self.data_window.date_from}..{self.data_window.end_exclusive}",
            )


def _parse_date_window(raw_constraints: dict[str, Any]) -> DataWindow | None:
    window = raw_constraints.get("data_window", {}).get("transactional")
    if not window:
        return None
    return DataWindow(
        date_from=_dt.date.fromisoformat(window["from"]),
        date_to_inclusive=_dt.date.fromisoformat(window["to"]),
        message_vi=window.get("message_vi", "").strip(),
    )


def load_catalog(
    entities_path: Path = DEFAULT_ENTITIES_PATH,
    metrics_path: Path = DEFAULT_METRICS_PATH,
) -> YamlCatalog:
    """Nap catalog tu dau tien - dung truc tiep khi can nap lai (test doi
    profile, trang admin reload). `get_catalog()` la ban co cache, nen dung
    o duong dan xu ly request thong thuong."""
    entities = _load_yaml(entities_path)
    metrics_raw = _load_yaml(metrics_path)

    datasets = {
        name: _build_dataset(name, raw)
        for name, raw in entities.get("datasets", {}).items()
    }
    dimensions = {
        name: _build_dimension(name, raw)
        for name, raw in entities.get("dimensions", {}).items()
    }
    metrics = {
        name: _build_metric(name, raw)
        for name, raw in metrics_raw.get("metrics", {}).items()
    }

    for m in metrics.values():
        if m.computed_by is None and m.dataset not in datasets:
            raise CatalogValidationError(
                f"chi so '{m.name}' tham chieu dataset khong ton tai: '{m.dataset}'",
                metric=m.name, dataset=m.dataset,
            )

    constraints = entities.get("constraints", {})
    forbidden = {
        spec["id"]: spec.get("reason_vi", "").strip()
        for spec in constraints.get("forbidden_metrics", [])
    }
    data_window = _parse_date_window(constraints)

    return YamlCatalog(
        version=f"{metrics_raw.get('version', '0')}+{entities.get('version', '0')}",
        datasets=datasets,
        dimensions=dimensions,
        metrics=metrics,
        forbidden_metrics=forbidden,
        data_window=data_window,
        max_rows=int(constraints.get("max_rows_per_query", 1000)),
        default_limit=int(constraints.get("default_limit", 100)),
    )


@lru_cache(maxsize=1)
def get_catalog() -> YamlCatalog:
    """Catalog nap mot lan, dung chung trong tien trinh - dung o duong dan
    request. Goi `get_catalog.cache_clear()` sau khi sua metrics.yml qua
    trang admin (T13) de nap lai."""
    return load_catalog()


__all__ = [
    "YamlCatalog", "DataWindow", "ForbiddenMetricSpec",
    "load_catalog", "get_catalog",
    "DEFAULT_ENTITIES_PATH", "DEFAULT_METRICS_PATH",
]
