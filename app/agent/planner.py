"""PLAN: playbook + entity -> danh sach MetricRequest (0 goi LLM). Xem
docs/06-agent-design.md muc 6.1.

Mot section co the tron chi so tu NHIEU dataset (vi du "funnel" trong
campaign_overview.yml: `leads` o dataset campaign_daily, `applications` o
dataset application) - compiler chi cho MOT dataset moi truy van (bat bien
1, docs/05 muc 5.3), nen Planner TACH mot section nhu vay thanh nhieu
MetricRequest (moi dataset mot cai); orchestrator chay rieng roi GHEP Fact
lai theo cac dimension chung (`merge_keys`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import cast

from app.agent.playbooks import Playbook, PlaybookSection
from app.contracts import DateRange, Filter, FilterOp, MetricRequest
from app.errors import MissingEntityError
from app.semantic.catalog import YamlCatalog


@dataclass(frozen=True, slots=True)
class DatasetRequest:
    dataset: str
    request: MetricRequest
    dataset_override: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedSection:
    section: PlaybookSection
    dataset_requests: tuple[DatasetRequest, ...] = ()  # rong neu section.source != None
    merge_keys: tuple[str, ...] = ()          # dimension dung de ghep Fact khi > 1 dataset_requests
    skipped_metrics: tuple[str, ...] = ()     # chi so computed_by da bi loc


def _resolve_date_range(playbook: Playbook) -> DateRange | None:
    if not playbook.default_date_range:
        return None
    d = playbook.default_date_range
    start = dt.date.fromisoformat(d["from"])
    end = dt.date.fromisoformat(d["to"])
    return DateRange(start=start, end_exclusive=end + dt.timedelta(days=1))


def _resolve_filters(
    section: PlaybookSection, entities: dict[str, list[str]]
) -> tuple[Filter, ...]:
    filters: list[Filter] = []
    for f in section.filters:
        if f.value_from_entity:
            values = entities.get(f.value_from_entity)
            if not values:
                continue  # entity khong bat buoc cho section nay - bo qua filter
            value = values[0] if f.op == "eq" else values
            filters.append(Filter(dimension=f.dimension, op=cast(FilterOp, f.op), value=value))
        elif f.value is not None:
            filters.append(Filter(dimension=f.dimension, op=cast(FilterOp, f.op), value=f.value))
    return tuple(filters)


class Planner:
    """Trien khai buoc PLAN. `plan()` khong cham DB - chi sinh MetricRequest."""

    def __init__(self, catalog: YamlCatalog) -> None:
        self.catalog = catalog

    def plan(self, playbook: Playbook, entities: dict[str, list[str]]) -> list[PlannedSection]:
        missing = [e for e in playbook.requires_entities if not entities.get(e)]
        if missing:
            raise MissingEntityError(
                f"thieu entity bat buoc cho playbook '{playbook.id}': {missing}",
                playbook=playbook.id, missing=missing,
            )

        date_range = _resolve_date_range(playbook)
        planned: list[PlannedSection] = []

        for section in playbook.sections:
            if section.source is not None:
                # "actions" | "sql_tool" | "static" | "derived" - xu ly rieng
                # trong buoc COMPUTE/ANALYZE cua orchestrator, khong qua metric_tool.
                planned.append(PlannedSection(section=section))
                continue

            if not section.metrics:
                continue

            usable_metrics, skipped = self._split_computed_metrics(section.metrics)
            if not usable_metrics:
                planned.append(PlannedSection(section=section, skipped_metrics=tuple(skipped)))
                continue

            filters = _resolve_filters(section, entities)
            groups = self._group_by_dataset(usable_metrics, section.dataset)

            if len(groups) == 1:
                ((ds_name, metric_names),) = groups.items()
                req = MetricRequest(
                    metrics=tuple(metric_names), dimensions=section.group_by, filters=filters,
                    date_range=date_range, order_by=section.order_by,
                    order_desc=section.order_desc, having=section.having,
                )
                dr = DatasetRequest(
                    dataset=ds_name, request=req,
                    dataset_override=section.dataset if section.dataset != ds_name else None,
                )
                planned.append(PlannedSection(
                    section=section, dataset_requests=(dr,), skipped_metrics=tuple(skipped),
                ))
                continue

            # Nhieu dataset: moi dataset MOT MetricRequest rieng, chi giu group_by
            # dim nao THUC SU thuoc dataset do; ORDER BY/HAVING chi giu o dataset
            # co chua ten do (tranh sinh ORDER BY tren ten khong co trong SELECT).
            # `catalog.dimension(d, "")` KHONG kiem tra dataset (chuoi rong la
            # falsy trong dieu kien cua chinh ham do) - dung de doc `.datasets`
            # an toan, tranh UnknownDimensionError khi dim khong thuoc dataset dang xet.
            dataset_requests: list[DatasetRequest] = []
            merge_keys = tuple(
                d for d in section.group_by
                if all(ds in self.catalog.dimension(d, "").datasets for ds in groups)
            )
            for ds_name, metric_names in groups.items():
                dims_for_ds = tuple(
                    d for d in section.group_by
                    if ds_name in self.catalog.dimension(d, "").datasets
                )
                has_order_metric = section.order_by in metric_names or section.order_by in dims_for_ds
                req = MetricRequest(
                    metrics=tuple(metric_names), dimensions=dims_for_ds, filters=filters,
                    date_range=date_range,
                    order_by=section.order_by if has_order_metric else None,
                    order_desc=section.order_desc,
                    having=section.having if section.having and _having_refs(
                        section.having, metric_names
                    ) else None,
                )
                dataset_requests.append(DatasetRequest(dataset=ds_name, request=req))

            planned.append(PlannedSection(
                section=section, dataset_requests=tuple(dataset_requests),
                merge_keys=merge_keys, skipped_metrics=tuple(skipped),
            ))

        return planned

    def _split_computed_metrics(self, metric_names: tuple[str, ...]) -> tuple[list[str], list[str]]:
        """Tach cac chi so `computed_by` (tinh boi Python, khong qua SQL
        compiler - vi du clv_predicted) ra khoi danh sach - orchestrator se
        tinh chung rieng qua clv_tool va gop lai thanh derived fact."""
        usable: list[str] = []
        skipped: list[str] = []
        for name in metric_names:
            metric = self.catalog.metric(name)
            (skipped if metric.computed_by is not None else usable).append(name)
        return usable, skipped

    def _group_by_dataset(
        self, metric_names: list[str], dataset_override: str | None,
    ) -> dict[str, list[str]]:
        """Nhom chi so theo dataset GOC cua chung (khong ap dataset_override o
        day - override chi hop le khi CHI mot dataset duy nhat dang dung, xu
        ly rieng o nhanh 1-dataset ben tren)."""
        groups: dict[str, list[str]] = {}
        for name in metric_names:
            ds = self.catalog.metric(name).dataset
            groups.setdefault(ds, []).append(name)
        return groups


def _having_refs(having: str, metric_names: list[str]) -> bool:
    return any(having.strip().startswith(name) for name in (*metric_names, "_n_rows"))


__all__ = ["Planner", "PlannedSection", "DatasetRequest"]
