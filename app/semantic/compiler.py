"""MetricRequest -> CompiledQuery. Xem docs/05-semantic-layer.md muc 5.3.

NAM BAT BIEN (kiem trong tests/test_semantic_compiler.py) - moi cai chan mot
loi bia:
  1. Ten bang/cot CHI lay tu catalog, khong bao gio tu input nguoi dung.
  2. Gia tri filter LUON di qua bind parameter (":ten") - khong noi chuoi.
  3. LUON co LIMIT.
  4. LUON them "COUNT(*) AS _n_rows" - can cho canh bao mau nho o 08 muc 4.
  5. ORDER BY chi nhan ten da co trong SELECT.

R2 (CLAUDE.md): khong noi du lieu nguoi dung vao SQL. Dieu nay ap dung ca cho
`MetricRequest.having`, mot truong chuoi tu do trong contracts.py - vi vay no
duoc parse bang mot ngu phap toi thieu ("<ten_da_chon> <toan_tu> <so>") thay
vi noi thang vao cau SQL.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.contracts import CompiledQuery, Filter, FilterOp, MetricRequest
from app.errors import DimensionNotAllowedError, ForbiddenMetricError, InvalidFilterError
from app.semantic.catalog import YamlCatalog

_OP_SYMBOL: dict[FilterOp, str] = {
    "eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
}

_HAVING_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|!=|=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$"
)


@dataclass(frozen=True, slots=True)
class _FilterSql:
    clause: str
    params: dict[str, Any]


def _validate_filter_value(dim: Any, f: Filter) -> None:
    """Khi dimension co `allowed_values` (chot cung), gia tri filter phai
    nam trong do - chan viec loc theo mot gia tri bia (vi du campaign_id la
    "CMP-KHONG-TON-TAI")."""
    if dim.allowed_values is None:
        return
    values = f.value if f.op in ("in", "not_in") else [f.value]
    unknown = [v for v in values if str(v) not in dim.allowed_values]
    if unknown:
        raise InvalidFilterError(
            f"gia tri khong hop le cho dimension '{f.dimension}': {unknown} "
            f"(chi nhan {dim.allowed_values})",
            dimension=f.dimension, values=unknown,
        )


def _compile_one_filter(catalog: YamlCatalog, dataset_name: str, idx: int, f: Filter) -> _FilterSql:
    dim = catalog.dimension(f.dimension, dataset_name)
    _validate_filter_value(dim, f)
    col = dim.column

    if f.op in _OP_SYMBOL:
        pname = f"f{idx}"
        return _FilterSql(f"{col} {_OP_SYMBOL[f.op]} :{pname}", {pname: f.value})

    if f.op in ("in", "not_in"):
        values = f.value
        if not isinstance(values, list | tuple) or not values:
            raise InvalidFilterError(
                f"filter '{f.op}' can mot danh sach gia tri khong rong, nhan: {f.value!r}",
                dimension=f.dimension,
            )
        names = [f"f{idx}_{j}" for j in range(len(values))]
        params = dict(zip(names, values, strict=True))
        placeholders = ", ".join(f":{n}" for n in names)
        kw = "IN" if f.op == "in" else "NOT IN"
        return _FilterSql(f"{col} {kw} ({placeholders})", params)

    if f.op == "between":
        if not isinstance(f.value, list | tuple) or len(f.value) != 2:
            raise InvalidFilterError(
                f"filter 'between' can (thap, cao), nhan: {f.value!r}", dimension=f.dimension
            )
        lo_name, hi_name = f"f{idx}_lo", f"f{idx}_hi"
        lo, hi = f.value
        return _FilterSql(
            f"{col} BETWEEN :{lo_name} AND :{hi_name}", {lo_name: lo, hi_name: hi}
        )

    raise InvalidFilterError(f"toan tu filter khong duoc ho tro: '{f.op}'", dimension=f.dimension)


def _compile_filters(
    catalog: YamlCatalog, dataset_name: str, filters: tuple[Filter, ...]
) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for idx, f in enumerate(filters):
        compiled = _compile_one_filter(catalog, dataset_name, idx, f)
        clauses.append(compiled.clause)
        params.update(compiled.params)
    return clauses, params


def _compile_having(having: str, selected_names: set[str]) -> tuple[str, dict[str, Any]]:
    m = _HAVING_RE.match(having)
    if not m:
        raise InvalidFilterError(
            f"having khong hop le: '{having}' - chi ho tro dang "
            f"'<ten_da_chon> <toan_tu> <so>', vi du 'n_disbursed >= 30'"
        )
    name, op, value = m.groups()
    if name not in selected_names:
        raise InvalidFilterError(
            f"having tham chieu ten '{name}' khong nam trong SELECT: {sorted(selected_names)}"
        )
    return f"{name} {op} :having_value", {"having_value": float(value)}


def _query_id(sql: str, params: dict[str, Any]) -> str:
    payload = sql + "|" + repr(sorted(params.items(), key=lambda kv: kv[0]))
    return "q_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


class MetricCompiler:
    """Trien khai `app.contracts.QueryCompiler`."""

    def __init__(self, catalog: YamlCatalog) -> None:
        self.catalog = catalog

    def compile(self, req: MetricRequest) -> CompiledQuery:
        if not req.metrics:
            raise InvalidFilterError("MetricRequest phai co it nhat mot chi so trong 'metrics'")

        metrics = [self.catalog.metric(name) for name in req.metrics]
        computed = [m for m in metrics if m.computed_by is not None]
        if computed:
            raise ForbiddenMetricError(
                "chi so tinh boi Python khong compile duoc qua SQL, goi qua "
                f"MetricRunner/computed_by: {[m.name for m in computed]}",
                metrics=[m.name for m in computed],
            )

        datasets_used = {m.dataset for m in metrics}
        if len(datasets_used) > 1:
            raise InvalidFilterError(
                "khong the gop cac chi so tu nhieu dataset khac nhau trong mot "
                f"truy van: {sorted(datasets_used)} (chi so: {list(req.metrics)})"
            )
        ds = self.catalog.dataset(next(iter(datasets_used)))

        dims = []
        for dname in req.dimensions:
            dim = self.catalog.dimension(dname, ds.name)
            for m in metrics:
                if m.allowed_dimensions and dname not in m.allowed_dimensions:
                    raise DimensionNotAllowedError(
                        f"dimension '{dname}' khong duoc phep voi chi so '{m.name}' "
                        f"(chi cho phep: {m.allowed_dimensions})",
                        metric=m.name, dimension=dname,
                    )
            dims.append(dim)

        select = [f"{d.column} AS {d.name}" for d in dims]
        select += [f"({m.sql}) AS {m.name}" for m in metrics]
        select.append("COUNT(*) AS _n_rows")  # bat bien 4: luon co co mau

        where: list[str] = []
        params: dict[str, Any] = {}

        f_clauses, f_params = _compile_filters(self.catalog, ds.name, req.filters)
        where.extend(f_clauses)
        params.update(f_params)

        if req.date_range:
            self.catalog.check_data_window(req.date_range.start, req.date_range.end_exclusive)
            if not ds.default_date_column:
                raise InvalidFilterError(
                    f"dataset '{ds.name}' khong co default_date_column, khong loc duoc theo ky"
                )
            where.append(
                f"{ds.default_date_column} >= :d_from AND {ds.default_date_column} < :d_to"
            )
            params["d_from"] = req.date_range.start
            params["d_to"] = req.date_range.end_exclusive

        selected_names = {d.name for d in dims} | {m.name for m in metrics} | {"_n_rows"}

        having_clause = ""
        if req.having:
            clause, having_params = _compile_having(req.having, selected_names)
            having_clause = f" HAVING {clause}"
            params.update(having_params)

        order_clause = ""
        if req.order_by:
            if req.order_by not in selected_names:  # bat bien 5
                raise InvalidFilterError(
                    f"order_by '{req.order_by}' khong nam trong SELECT: {sorted(selected_names)}"
                )
            order_clause = f" ORDER BY {req.order_by} {'DESC' if req.order_desc else 'ASC'}"

        limit = min(req.limit or self.catalog.default_limit, self.catalog.max_rows)  # bat bien 3

        sql = (
            f"SELECT {', '.join(select)} FROM {ds.table}"
            + (f" WHERE {' AND '.join(where)}" if where else "")
            + (f" GROUP BY {', '.join(d.name for d in dims)}" if dims else "")
            + having_clause
            + order_clause
            + f" LIMIT {limit}"
        )

        caveats = [m.caveat_vi for m in metrics if m.caveat_vi]
        if ds.caveat_vi:
            caveats.append(ds.caveat_vi)

        return CompiledQuery(
            query_id=_query_id(sql, params),
            sql=sql,
            params=params,
            metrics=tuple(metrics),
            dimensions=tuple(dims),
            caveats=tuple(dict.fromkeys(c.strip() for c in caveats)),  # loai trung, giu thu tu
        )


__all__ = ["MetricCompiler"]
