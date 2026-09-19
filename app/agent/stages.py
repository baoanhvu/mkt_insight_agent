"""Nap `config/stages.yaml` (protected), tinh tien trinh cong don theo
`weight`. Xem docs/15-streaming.md muc 15.2.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STAGES_PATH = ROOT / "config" / "stages.yaml"

# Thu tu giai doan trong may trang thai (docs/06 muc 6.1). `judging` co
# weight=0 (bat dong bo, ngoai duong gang) nen khong anh huong toi progress.
STAGE_ORDER: tuple[str, ...] = (
    "intake", "routing", "planning", "computing", "analyzing",
    "narrating", "verifying", "rendering", "judging",
)


class StagesConfig:
    def __init__(self, path: Path = DEFAULT_STAGES_PATH) -> None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.version: str = str(raw.get("version", "0"))
        self.stages: dict[str, dict[str, Any]] = raw.get("stages", {})
        self.overrides: dict[str, dict[str, str]] = raw.get("playbook_overrides", {})
        self.special: dict[str, dict[str, Any]] = raw.get("special", {})
        self.sse: dict[str, Any] = raw.get("sse", {})
        self._total_weight = sum(s.get("weight", 0) for s in self.stages.values())

    def label(self, stage: str, playbook_id: str | None = None, **fmt: Any) -> str:
        """Nhan tieng Viet cho mot giai doan, uu tien override cua playbook."""
        if playbook_id and playbook_id in self.overrides:
            override = self.overrides[playbook_id].get(stage)
            if override:
                return override
        spec = self.stages.get(stage, {})
        template = spec.get("template_vi")
        if template and fmt:
            return str(template).format(**fmt)
        return str(spec.get("label_vi", stage))

    def weight(self, stage: str) -> float:
        return float(self.stages.get(stage, {}).get("weight", 0))

    def progress_after(self, completed_stages: list[str]) -> float:
        """Ty le tien trinh (0..1) sau khi hoan thanh danh sach giai doan da cho."""
        if not self._total_weight:
            return 0.0
        done = sum(self.weight(s) for s in completed_stages)
        return float(min(1.0, done / self._total_weight))

    def special_label(self, key: str, **fmt: Any) -> str:
        spec = self.special.get(key, {})
        template = spec.get("label_vi", key)
        try:
            return str(template).format(**fmt)
        except (KeyError, IndexError):
            return str(template)


@lru_cache(maxsize=1)
def get_stages_config() -> StagesConfig:
    return StagesConfig()


__all__ = ["StagesConfig", "get_stages_config", "STAGE_ORDER"]
