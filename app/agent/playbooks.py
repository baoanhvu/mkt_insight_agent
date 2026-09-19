"""Nap `config/playbooks/*.yml` (protected). Xem docs/06-agent-design.md muc 6.3.

Anh xa intent -> playbook nam O DAY, khong nam trong code: them mot loai
phan tich moi nghia la them mot file YAML, khong sua Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PLAYBOOKS_DIR = ROOT / "config" / "playbooks"


@dataclass(frozen=True, slots=True)
class SectionFilter:
    dimension: str
    op: str
    value: Any = None
    value_from_entity: str | None = None


@dataclass(frozen=True, slots=True)
class PlaybookSection:
    id: str
    label_vi: str
    fact_id: str | None = None
    metrics: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ()
    filters: tuple[SectionFilter, ...] = ()
    order_by: str | None = None
    order_desc: bool = True
    having: str | None = None
    max_words: int | None = None
    skip_if_empty: bool = False
    source: str | None = None  # None = metric_tool; "actions" | "sql_tool" | "static"
    max_items: int | None = None
    min_priority: int | None = None
    always_show: bool = False
    dataset: str | None = None  # override dataset cua chi so - xem app/agent/planner.py
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class Playbook:
    id: str
    label_vi: str
    intent: str  # da chuan hoa ve chu thuong, khop app.contracts.Intent.value
    requires_entities: tuple[str, ...]
    prompt: str
    comparison_policy: str
    sections: tuple[PlaybookSection, ...]
    default_date_range: dict[str, str] | None = None
    max_words: int | None = None
    required_caveats: tuple[dict[str, Any], ...] = ()
    on_missing_entity: dict[str, Any] | None = None
    charts: tuple[dict[str, Any], ...] = ()
    sql_guard: dict[str, Any] | None = None
    self_consistency: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


def _build_section(raw: dict[str, Any]) -> PlaybookSection:
    filters = tuple(
        SectionFilter(
            dimension=f["dimension"], op=f["op"], value=f.get("value"),
            value_from_entity=f.get("value_from_entity"),
        )
        for f in (raw.get("filters") or [])
    )
    return PlaybookSection(
        id=raw["id"], label_vi=raw.get("label_vi", raw["id"]),
        fact_id=raw.get("fact_id"), metrics=tuple(raw.get("metrics") or ()),
        group_by=tuple(raw.get("group_by") or ()), filters=filters,
        order_by=raw.get("order_by"), order_desc=bool(raw.get("order_desc", True)),
        having=raw.get("having"), max_words=raw.get("max_words"),
        skip_if_empty=bool(raw.get("skip_if_empty", False)), source=raw.get("source"),
        max_items=raw.get("max_items"), min_priority=raw.get("min_priority"),
        always_show=bool(raw.get("always_show", False)), dataset=raw.get("dataset"),
        raw=raw,
    )


def _build_playbook(raw: dict[str, Any]) -> Playbook:
    return Playbook(
        id=raw["id"], label_vi=raw.get("label_vi", raw["id"]),
        intent=str(raw["intent"]).lower(),
        requires_entities=tuple(raw.get("requires_entities") or ()),
        prompt=raw["prompt"],
        comparison_policy=raw.get("comparison_policy", "significance_required"),
        sections=tuple(_build_section(s) for s in (raw.get("sections") or [])),
        default_date_range=raw.get("default_date_range"),
        max_words=raw.get("max_words"),
        required_caveats=tuple(raw.get("required_caveats") or ()),
        on_missing_entity=raw.get("on_missing_entity"),
        charts=tuple(raw.get("charts") or ()),
        sql_guard=raw.get("sql_guard"),
        self_consistency=raw.get("self_consistency"),
        raw=raw,
    )


class PlaybookStore:
    def __init__(self, root: Path = DEFAULT_PLAYBOOKS_DIR) -> None:
        self.root = root
        self._by_id: dict[str, Playbook] = {}
        self._by_intent: dict[str, Playbook] = {}
        self._load_all()

    def _load_all(self) -> None:
        for path in sorted(self.root.glob("*.yml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            pb = _build_playbook(raw)
            self._by_id[pb.id] = pb
            self._by_intent[pb.intent] = pb

    def get(self, playbook_id: str) -> Playbook:
        return self._by_id[playbook_id]

    def for_intent(self, intent: str) -> Playbook | None:
        return self._by_intent.get(intent.lower())

    def all(self) -> tuple[Playbook, ...]:
        return tuple(self._by_id.values())


@lru_cache(maxsize=1)
def get_playbook_store() -> PlaybookStore:
    return PlaybookStore()


__all__ = [
    "Playbook", "PlaybookSection", "SectionFilter", "PlaybookStore", "get_playbook_store",
]
