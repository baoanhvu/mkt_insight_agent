"""Nap cau hinh theo thu tu: app.yaml -> profiles/{PROFILE}.yaml -> secrets.yaml
-> bien moi truong. Xem docs/10-config-secrets.md.

Day la LOP DUY NHAT trong toan bo ung dung duoc phep goi `os.environ` de lay bi
mat (quy tac 3 o docs/10 muc 10.5). Khong noi nao khac trong app/ duoc doc
os.environ truc tiep - luon di qua `get_settings()`.

Co che giai quyet tham chieu, khoi tu file YAML:
    database:
      url_from_secret: "database.url"      -> tra o config/secrets.yaml
    llm:
      model_from_env: "LLM_MODEL"           -> tra o bien moi truong
      model_fallback: "gpt-oss-mock"        -> dung khi bien moi truong chua dat

Bien moi truong ghi de truc tiep (thang tat ca) dung quy uoc:
    MKT_LLM__MODEL=... -> ghi de llm.model
    MKT_DATABASE__URL=... -> ghi de database.url
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.errors import ConfigError, MissingSecretError

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

_VALID_PROFILES = {"local", "greennode", "test"}
_ENV_PREFIX = "MKT_"
_SUFFIX_FROM_SECRET = "_from_secret"
_SUFFIX_FROM_ENV = "_from_env"
_SUFFIX_DEFAULT = "_default"
_SUFFIX_FALLBACK = "_fallback"


class ConfigNode:
    """Bao mot `dict` de truy cap duoc bang thuoc tinh, vi du `s.database.url`.

    Chi la lop tien ich hien thi - moi du lieu that nam trong `_data`. Truy cap
    mot khoa khong ton tai nem `AttributeError` (giong doi tuong Python binh
    thuong) de loi hien ra ngay tai noi dung, khong lan mo xuong tan cuoi ham.
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name: str) -> Any:
        try:
            value = self._data[name]
        except KeyError as exc:
            raise AttributeError(
                f"khong co khoa cau hinh '{name}' trong {sorted(self._data)}"
            ) from exc
        if isinstance(value, dict):
            return ConfigNode(value)
        return value

    def get(self, name: str, default: Any = None) -> Any:
        value = self._data.get(name, default)
        if isinstance(value, dict):
            return ConfigNode(value)
        return value

    def __contains__(self, name: str) -> bool:
        return name in self._data

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def __repr__(self) -> str:  # pragma: no cover - chi phuc vu debug
        return f"ConfigNode({self._data!r})"


_SECTION_NAMES = (
    "app", "database", "llm", "agent", "verify", "analytics",
    "ui", "logging", "telemetry", "admin", "greennode",
)


@dataclass(frozen=True)
class Settings:
    """Cau hinh da nap va giai quyet xong cho mot phien chay.

    Bat bien: khong truong nao con hau to `_from_secret` / `_from_env` /
    `_default` / `_fallback` sau khi `load_settings()` tra ve doi tuong nay.
    """

    profile: str
    raw: dict[str, Any]
    app: ConfigNode = field(init=False)
    database: ConfigNode = field(init=False)
    llm: ConfigNode = field(init=False)
    agent: ConfigNode = field(init=False)
    verify: ConfigNode = field(init=False)
    analytics: ConfigNode = field(init=False)
    ui: ConfigNode = field(init=False)
    logging: ConfigNode = field(init=False)
    telemetry: ConfigNode = field(init=False)
    admin: ConfigNode = field(init=False)
    greennode: ConfigNode = field(init=False)

    def __post_init__(self) -> None:
        for section in _SECTION_NAMES:
            object.__setattr__(self, section, ConfigNode(self.raw.get(section, {})))


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"file cau hinh khong phai mapping: {path}", path=str(path))
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Tron de qui hai dict; gia tri trong `override` thang o khoa trung nhau."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _lookup_dotted(data: dict[str, Any], dotted_path: str) -> Any:
    cur: Any = data
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise MissingSecretError(
                f"khong tim thay bi mat '{dotted_path}' trong config/secrets.yaml",
                secret_path=dotted_path,
            )
        cur = cur[part]
    return cur


def _resolve_refs(node: Any, secrets: dict[str, Any], env: dict[str, str]) -> Any:
    """Duyet de qui cay cau hinh, giai quyet cac khoa hau to dac biet.

    Thu tu ap dung tren mot nhom khoa cung goc (vi du `model_from_env` +
    `model_fallback` deu ung voi goc `model`):
      1. `<goc>_from_secret` - tra trong `secrets`, LOI ngay neu thieu
      2. `<goc>_from_env` - tra trong `env`; neu khong co thi de trong,
         cho `_default`/`_fallback` xu ly tiep hoac ghi de bang bien MKT_*
      3. `<goc>_default` / `<goc>_fallback` - dung khi hai buoc tren chua co
      4. khoa thuong - giu nguyen (hoac de qui neu la dict/list)
    """
    if isinstance(node, dict):
        resolved: dict[str, Any] = {}
        deferred_default: dict[str, Any] = {}
        for key, value in node.items():
            if key.endswith(_SUFFIX_FROM_SECRET):
                root = key[: -len(_SUFFIX_FROM_SECRET)]
                resolved[root] = _lookup_dotted(secrets, value)
            elif key.endswith(_SUFFIX_FROM_ENV):
                root = key[: -len(_SUFFIX_FROM_ENV)]
                if value in env:
                    resolved[root] = env[value]
            elif key.endswith(_SUFFIX_DEFAULT) or key.endswith(_SUFFIX_FALLBACK):
                suffix_len = len(_SUFFIX_DEFAULT if key.endswith(_SUFFIX_DEFAULT) else _SUFFIX_FALLBACK)
                root = key[:-suffix_len]
                deferred_default[root] = value
            else:
                resolved[key] = _resolve_refs(value, secrets, env)
        for root, default_value in deferred_default.items():
            resolved.setdefault(root, default_value)
        return resolved
    if isinstance(node, list):
        return [_resolve_refs(item, secrets, env) for item in node]
    return node


def _apply_env_overrides(data: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    """Ap `MKT_A__B__C=value` -> `data['a']['b']['c'] = value`.

    Kieu du lieu duoc suy ra bang chinh `yaml.safe_load` tren gia tri chuoi, vi
    vay "8" -> int 8, "true" -> bool True, "0.85" -> float - giong cach YAML
    hieu, dung nhu tai lieu mo ta ("MKT_VERIFY__T_HIGH=0.88").
    """
    result = copy.deepcopy(data)
    for env_key, raw_value in sorted(env.items()):
        if not env_key.startswith(_ENV_PREFIX):
            continue
        path = env_key[len(_ENV_PREFIX):].lower().split("__")
        if not all(path):
            continue
        parsed_value = yaml.safe_load(raw_value)
        node = result
        for part in path[:-1]:
            existing = node.get(part)
            if not isinstance(existing, dict):
                existing = {}
            node[part] = existing
            node = existing
        node[path[-1]] = parsed_value
    return result


def load_settings(profile: str | None = None) -> Settings:
    """Nap Settings tu dau, khong dung cache. `get_settings()` la ham nen dung."""
    resolved_profile = profile or os.environ.get("APP_PROFILE", "local")
    if resolved_profile not in _VALID_PROFILES:
        raise ConfigError(
            f"APP_PROFILE khong hop le: '{resolved_profile}'. "
            f"Chi nhan {sorted(_VALID_PROFILES)}.",
            profile=resolved_profile,
        )

    app_cfg = _load_yaml(CONFIG_DIR / "app.yaml")
    profile_cfg = _load_yaml(CONFIG_DIR / "profiles" / f"{resolved_profile}.yaml")
    merged = _deep_merge(app_cfg, profile_cfg)

    secrets_path = CONFIG_DIR / "secrets.yaml"
    secrets = _load_yaml(secrets_path)

    env = dict(os.environ)
    resolved = _resolve_refs(merged, secrets, env)
    resolved = _apply_env_overrides(resolved, env)

    return Settings(profile=resolved_profile, raw=resolved)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Diem nap cau hinh nen dung o moi noi khac trong ung dung. Ket qua duoc
    cache trong tien trinh - goi `clear_settings_cache()` truoc khi nap lai
    (chi can trong test doi profile giua cac ca kiem thu)."""
    return load_settings()


def clear_settings_cache() -> None:
    """Xoa cache cua `get_settings()`. Dung trong test khi can APP_PROFILE khac
    nhau trong cung mot phien pytest."""
    get_settings.cache_clear()


__all__ = ["ConfigNode", "Settings", "load_settings", "get_settings", "clear_settings_cache"]
