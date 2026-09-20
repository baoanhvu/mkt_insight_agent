"""`PromptLoader` - nap `prompts/*.yaml`, hot-reload theo mtime, render Jinja2.
Trien khai `app.contracts.PromptStore`. Xem docs/07-prompt-fewshot.md muc 7.4.

QUY TAC:
  - Jinja2 CHI render `system` va `instructions`. `few_shots` chen NGUYEN VAN -
    neu khong, cac the {{F1.r1.romi}} trong vi du mau se bi Jinja2 nuot mat
    (coi la bien can thay the) truoc khi kip toi tay Narrator.
  - Parse loi -> GIU NGUYEN ban dang chay trong cache, ghi log loi. Mot file
    .yaml hong KHONG BAO GIO duoc lam sap agent dang phuc vu request khac.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jinja2
import yaml

from app.contracts import RenderedPrompt
from app.errors import PromptValidationError
from app.logging_ import get_logger

log = get_logger(__name__)

DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_REQUIRED_KEYS = ("id", "version", "model_role")

# Cac prompt narrator dung `system` de day mau the vi du NGUYEN VAN cho LLM
# doc, vi du "phai viet duoi dang the {{fact_id}}... Vi du dung: {{F1.r1.romi}}".
# Do KHONG phai bien Jinja can render - khong bao gio co ctx ten "fact_id"
# hay "F1" duoc truyen vao. Chi khop dinh danh don gian (chu/so/gach duoi/dau
# cham, KHONG khoang trang/toan tu/pipe) nen KHONG dung nham voi Jinja THAT
# trong `instructions` (vi du "{{ s.label_vi }}", "{{ tone | default(...) }}"
# - hai mau nay co pipe/space quanh dau cham hoac ham goi, khong khop). Kiem
# chung tren ca 9 file: mau nay CHI xuat hien trong `system`, khong bao gio
# trong `instructions`.
_LITERAL_TAG_RE = re.compile(r"\{\{\s*[A-Za-z0-9_.]+\s*\}\}")


def _escape_literal_tags(template_src: str) -> str:
    return _LITERAL_TAG_RE.sub(lambda m: "{% raw %}" + m.group(0) + "{% endraw %}", template_src)


@dataclass(slots=True)
class _CachedPrompt:
    data: dict[str, Any]
    mtime: float


def _validate_prompt_dict(
    prompt_id: str, data: dict[str, Any], env: jinja2.Environment
) -> list[str]:
    """Kiem tra truoc khi dung: bien Jinja co parse duoc, few-shot co du
    field, output_contract.forbidden_patterns co compile duoc. Tra ve danh
    sach chuoi loi (rong = hop le) - khop `PromptStore.validate()`."""
    errors: list[str] = []

    for key in _REQUIRED_KEYS:
        if not data.get(key):
            errors.append(f"thieu khoa bat buoc '{key}'")

    if data.get("id") and data["id"] != prompt_id:
        errors.append(f"khoa 'id'='{data['id']}' khong khop ten file '{prompt_id}'")

    for field_name in ("system", "instructions"):
        template_src = data.get(field_name, "")
        if template_src and not isinstance(template_src, str):
            errors.append(f"'{field_name}' phai la chuoi")
            continue
        src = _escape_literal_tags(template_src or "") if field_name == "system" else (template_src or "")
        try:
            env.parse(src)
        except jinja2.TemplateSyntaxError as exc:
            errors.append(f"'{field_name}' loi cu phap Jinja2: {exc}")

    few_shots = data.get("few_shots") or []
    if not isinstance(few_shots, list):
        errors.append("'few_shots' phai la danh sach")
    else:
        for i, shot in enumerate(few_shots):
            if not isinstance(shot, dict):
                errors.append(f"few_shots[{i}] phai la mapping")
                continue
            if "output" not in shot:
                errors.append(f"few_shots[{i}] thieu 'output'")
            # Khong bat buoc 'input'/'evidence': mot so prompt (clarify_question,
            # refuse_out_of_scope) mo ta ngu canh bang chinh cac bien Jinja cua
            # `instructions` (question/reason/options...) thay vi mot chuoi
            # "input" don le - xem nhanh render() ve cach dung lai.

    params = data.get("params")
    if params is not None and not isinstance(params, dict):
        errors.append("'params' phai la mapping")

    contract = data.get("output_contract")
    if contract is not None:
        if not isinstance(contract, dict):
            errors.append("'output_contract' phai la mapping")
        else:
            for j, pat_spec in enumerate(contract.get("forbidden_patterns") or []):
                if not isinstance(pat_spec, dict) or "pattern" not in pat_spec:
                    errors.append(f"output_contract.forbidden_patterns[{j}] thieu 'pattern'")
                    continue
                try:
                    re.compile(pat_spec["pattern"])
                except re.error as exc:
                    errors.append(
                        f"output_contract.forbidden_patterns[{j}] pattern khong hop le: {exc}"
                    )

    return errors


class PromptLoader:
    """Trien khai `app.contracts.PromptStore`."""

    def __init__(self, root: Path = DEFAULT_PROMPTS_DIR, watch: bool = True) -> None:
        self.root = root
        self.watch = watch
        self._cache: dict[str, _CachedPrompt] = {}
        self._env = jinja2.Environment(
            loader=jinja2.BaseLoader(), autoescape=False, undefined=jinja2.StrictUndefined,
        )

    def _path_for(self, prompt_id: str) -> Path:
        return self.root / f"{prompt_id}.yaml"

    def _mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return -1.0

    def _parse(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise PromptValidationError(f"khong tim thay file prompt: {path}", path=str(path))
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PromptValidationError(
                f"loi cu phap YAML: {path} -> {exc}", path=str(path)
            ) from exc
        if not isinstance(raw, dict):
            raise PromptValidationError(f"prompt khong phai mapping YAML: {path}", path=str(path))
        return raw

    def get(self, prompt_id: str) -> dict[str, Any]:
        """Tra ve prompt da parse (dict thuan). Kiem tra mtime, tu nap lai
        neu file doi; parse loi thi giu nguyen ban dang chay."""
        path = self._path_for(prompt_id)
        cached = self._cache.get(prompt_id)
        current_mtime = self._mtime(path)

        if cached is not None and (not self.watch or current_mtime == cached.mtime):
            return cached.data

        try:
            data = self._parse(path)
            errors = _validate_prompt_dict(prompt_id, data, self._env)
            if errors:
                raise PromptValidationError(
                    f"prompt '{prompt_id}' khong hop le: {'; '.join(errors)}",
                    prompt_id=prompt_id, errors=errors,
                )
        except PromptValidationError as exc:
            if cached is not None:
                log.error("prompt_reload_failed_keep_running", prompt_id=prompt_id,
                          error=str(exc))
                return cached.data
            raise  # lan dau nap ma da loi -> khong co ban nao de giu, phai bao

        self._cache[prompt_id] = _CachedPrompt(data=data, mtime=current_mtime)
        if cached is not None:
            log.info("prompt_reloaded", prompt_id=prompt_id, version=data.get("version"))
        return data

    def render(self, prompt_id: str, **ctx: Any) -> RenderedPrompt:
        """Render Jinja2 (`system`/`instructions`) -> messages OpenAI, giu
        nguyen `few_shots`. `ctx` thieu bien -> raise PromptValidationError
        (StrictUndefined) thay vi render ra chuoi rong lang le."""
        data = self.get(prompt_id)

        system_src = _escape_literal_tags(data.get("system", "") or "")
        try:
            system = self._env.from_string(system_src).render(**ctx).strip()
            instructions = self._env.from_string(data.get("instructions", "")).render(**ctx).strip()
        except jinja2.UndefinedError as exc:
            raise PromptValidationError(
                f"prompt '{prompt_id}': thieu bien khi render - {exc}", prompt_id=prompt_id
            ) from exc

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})

        instructions_template = self._env.from_string(data.get("instructions", ""))
        for shot in data.get("few_shots") or []:
            if "output" not in shot:
                continue
            if "input" in shot:
                # route_intent, judge_grounding: mot chuoi "input" don le.
                user_content = str(shot["input"])
            elif "evidence" in shot:
                # narrate_*: EVIDENCE serialize truoc, giong dung invocation
                # thuc (Narrator T08 se dua EvidenceSet vao dung dang nay).
                # judge_grounding con co them 'statement' (cau can cham) -
                # thieu no thi vi du mau chi con EVIDENCE, khong day du nhu
                # mot loi goi that (T11).
                user_content = f"EVIDENCE:\n{shot['evidence']}"
                if "statement" in shot:
                    user_content += f"\n\nSTATEMENT:\n{shot['statement']}"
            else:
                # clarify_question, refuse_out_of_scope: cac truong con lai
                # (question/reason/options/...) CHINH LA bien cua `instructions`
                # - render lai bang chinh template do de vi du khop dung dang
                # ma mot request thuc se tao ra.
                shot_ctx = {k: v for k, v in shot.items() if k != "output"}
                try:
                    user_content = instructions_template.render(**shot_ctx).strip()
                except jinja2.UndefinedError:
                    user_content = str(shot_ctx)
            messages.append({"role": "user", "content": user_content})
            messages.append({"role": "assistant", "content": str(shot["output"])})

        if instructions:
            messages.append({"role": "user", "content": instructions})

        return RenderedPrompt(
            prompt_id=prompt_id, version=str(data.get("version", "0")),
            messages=messages, params=dict(data.get("params") or {}),
        )

    def validate(self, prompt_id: str) -> list[str]:
        """Kiem tra MOT prompt truc tiep tu dia (khong dung cache) - dung
        truoc khi luu qua trang admin (T13)."""
        path = self._path_for(prompt_id)
        try:
            data = self._parse(path)
        except PromptValidationError as exc:
            return [str(exc)]
        return _validate_prompt_dict(prompt_id, data, self._env)

    def validate_all(self) -> dict[str, list[str]]:
        """Kiem tra toan bo file `*.yaml` trong `root`. Tra ve
        {prompt_id: [loi...]} - CHI gom prompt co loi (rong = tat ca hop le)."""
        out: dict[str, list[str]] = {}
        for path in sorted(self.root.glob("*.yaml")):
            errs = self.validate(path.stem)
            if errs:
                out[path.stem] = errs
        return out


__all__ = ["PromptLoader", "DEFAULT_PROMPTS_DIR"]
