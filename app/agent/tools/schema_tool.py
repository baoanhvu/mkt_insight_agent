"""`schema_tool` - tra mo ta chi so/dimension BANG TIENG VIET cho LLM doc,
KHONG BAO GIO tra `CREATE TABLE` hay ten cot/bang tho. Dua schema DB tho cho
LLM chinh la mo cua cho no tu viet SQL tu do - dieu ma toan bo semantic layer
duoc thiet ke de tranh (docs/06-agent-design.md muc 6.4).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.semantic.catalog import YamlCatalog


@dataclass(frozen=True, slots=True)
class CatalogView:
    """Mo ta catalog bang tieng Viet, dang van ban de nhung vao prompt."""

    metrics_vi: str
    dimensions_vi: str


class SchemaTool:
    def __init__(self, catalog: YamlCatalog) -> None:
        self.catalog = catalog

    def describe(self, dataset: str | None = None) -> CatalogView:
        metrics_lines = []
        for m in self.catalog.all_metrics(dataset):
            if m.computed_by is not None:
                continue  # chi so tinh boi Python, khong compile SQL - bo qua o day
            line = f"- {m.name} ({m.label_vi}): don vi {m.unit}"
            if m.caveat_vi:
                line += f" - CHU Y: {m.caveat_vi.strip()}"
            metrics_lines.append(line)

        dim_lines = []
        for d in self.catalog.all_dimensions(dataset):
            line = f"- {d.name} ({d.label_vi})"
            if d.allowed_values:
                line += f": {', '.join(d.allowed_values)}"
            dim_lines.append(line)

        return CatalogView(
            metrics_vi="\n".join(sorted(metrics_lines)),
            dimensions_vi="\n".join(sorted(dim_lines)),
        )


__all__ = ["SchemaTool", "CatalogView"]
