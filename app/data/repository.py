"""Thuc thi `CompiledQuery` qua `engine_ro` va boc ket qua thanh `Fact` co dia
chi o (`app.contracts.MetricRunner`). Day la noi DUY NHAT trong ung dung goi
`conn.execute()` tren du lieu phuc vu cau tra loi - moi noi khac (agent,
verify) chi thay Fact/EvidenceSet, khong bao gio thay SQL hay engine.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from app.contracts import ColumnSpec, CompiledQuery, Fact, MetricRequest
from app.data.engines import get_engine_ro
from app.semantic.catalog import YamlCatalog, get_catalog
from app.semantic.compiler import MetricCompiler

# Nhan hien thi cho cot ky thuat "_n_rows" - cot nay do COMPILER tu chen vao
# moi truy van (bat bien 4, docs/05 muc 5.3), khong phai mot Metric khai bao
# trong metrics.yml nen khong co san label_vi de lay. Giu la mot hang so duy
# nhat o day, giong tien le fmt_vnd()/"VND" trong app/web/formatting.py.
_N_ROWS_LABEL_VI = "Cỡ mẫu"


class SqlMetricRunner:
    """Trien khai `app.contracts.MetricRunner`."""

    def __init__(self, catalog: YamlCatalog | None = None, engine: Engine | None = None) -> None:
        self.catalog = catalog or get_catalog()
        self.compiler = MetricCompiler(self.catalog)
        self._engine = engine

    @property
    def engine(self) -> Engine:
        return self._engine if self._engine is not None else get_engine_ro()

    def run(self, req: MetricRequest, fact_id: str, title: str) -> Fact:
        cq = self.compiler.compile(req)
        with self.engine.connect() as conn:
            result = conn.execute(text(cq.sql), cq.params)
            column_names = list(result.keys())
            raw_rows = result.mappings().all()

        columns = _build_column_specs(cq, column_names)
        rows: list[dict[str, Any]] = []
        for i, row in enumerate(raw_rows, start=1):
            row_dict: dict[str, Any] = {"_ref": f"{fact_id}.r{i}"}
            row_dict.update({name: row[name] for name in column_names})
            rows.append(row_dict)

        return Fact(
            fact_id=fact_id,
            title=title,
            query_id=cq.query_id,
            sql=cq.sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            caveats=list(cq.caveats),
        )


def _build_column_specs(cq: CompiledQuery, column_names: list[str]) -> list[ColumnSpec]:
    by_name: dict[str, ColumnSpec] = {}
    for d in cq.dimensions:
        by_name[d.name] = ColumnSpec(name=d.name, label=d.label_vi, unit="text", format="")
    for m in cq.metrics:
        by_name[m.name] = ColumnSpec(
            name=m.name, label=m.label_vi, unit=m.unit, format=m.format,
            higher_is_better=m.higher_is_better,
        )

    specs: list[ColumnSpec] = []
    for name in column_names:
        if name == "_n_rows":
            specs.append(ColumnSpec(name="_n_rows", label=_N_ROWS_LABEL_VI, unit="count",
                                     format="#,##0"))
        elif name in by_name:
            specs.append(by_name[name])
        else:  # phong ve: cot la khong ngo toi tu SQL (khong nen xay ra)
            specs.append(ColumnSpec(name=name, label=name, unit="text", format=""))
    return specs


__all__ = ["SqlMetricRunner"]
