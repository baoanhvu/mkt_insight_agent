"""Kiem tra app/prompts/loader.py. Xem docs/07-prompt-fewshot.md muc 7.4.

BAT BUOC (docs/17-implementation-guide.md T07):
  - loader.validate_all() -> khong loi tren ca 9 file
  - few_shot giu nguyen chuoi "{{F1.r1.romi}}"
  - YAML hong -> GIU NGUYEN ban dang chay, khong raise
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import PromptValidationError
from app.prompts.loader import PromptLoader

REAL_PROMPT_IDS = [
    "clarify_question", "judge_grounding", "narrate_campaign_diagnosis",
    "narrate_campaign_overview", "narrate_clv_actions", "narrate_funnel",
    "narrate_persona", "refuse_out_of_scope", "route_intent",
]


@pytest.fixture(scope="module")
def loader() -> PromptLoader:
    return PromptLoader()


def test_validate_all_has_no_errors_on_real_prompts(loader: PromptLoader) -> None:
    """BAT BUOC: loader.validate_all() -> khong loi tren ca 9 file."""
    errors = loader.validate_all()
    assert errors == {}, errors


def test_all_nine_real_prompts_discovered(loader: PromptLoader) -> None:
    for prompt_id in REAL_PROMPT_IDS:
        data = loader.get(prompt_id)
        assert data["id"] == prompt_id


def test_narrate_prompt_few_shot_preserves_evidence_tags_verbatim(loader: PromptLoader) -> None:
    """BAT BUOC: few_shot giu nguyen chuoi "{{F1.r1.romi}}" - Jinja2 KHONG
    duoc render few_shots (se nuot mat the), va he thong escape rieng cho
    cac vi du minh hoa the trong `system` khong duoc lam mat the trong
    `few_shots` (hai co che khac nhau, phai kiem ca hai)."""
    rp = loader.render(
        "narrate_campaign_diagnosis", tone="truc tiep", max_words=400,
        sections=[{"label_vi": "Kết luận"}],
    )
    assistant_contents = [m["content"] for m in rp.messages if m["role"] == "assistant"]
    assert any("{{F1.r1.net_profit}}" in c for c in assistant_contents)
    assert any("{{F1.r1.romi}}" in c for c in assistant_contents)


def test_system_prompt_illustrative_tag_examples_survive_jinja_render(loader: PromptLoader) -> None:
    """`system` cua narrate_campaign_diagnosis chua vi du minh hoa cu phap the
    NGUYEN VAN ("phai viet duoi dang the {{fact_id}}...") - day KHONG phai
    bien Jinja (khong co ctx ten 'fact_id'), nen phai duoc bao ve khoi Jinja2
    dien giai nham thanh bien roi bao loi UndefinedError."""
    rp = loader.render(
        "narrate_campaign_diagnosis", tone="truc tiep", max_words=400,
        sections=[{"label_vi": "Kết luận"}],
    )
    system_content = next(m["content"] for m in rp.messages if m["role"] == "system")
    assert "{{fact_id}}" in system_content
    assert "{{F1.r1.romi}}" in system_content


def test_instructions_jinja_variables_are_rendered_for_real(loader: PromptLoader) -> None:
    """Nguoc lai voi system: `instructions` PHAI render dung cac bien Jinja
    THAT (vi du vong lap qua `sections`) - khong duoc coi tat ca {{...}} la
    van ban tinh."""
    rp = loader.render(
        "narrate_campaign_diagnosis", tone="truc tiep", max_words=250,
        sections=[{"label_vi": "Phân rã chi phí"}],
    )
    user_contents = [m["content"] for m in rp.messages if m["role"] == "user"]
    assert any("Phân rã chi phí" in c for c in user_contents)
    assert any("250" in c for c in user_contents)


def test_clarify_question_few_shot_reconstructed_from_instructions_template(
    loader: PromptLoader,
) -> None:
    """clarify_question.yaml khong co truong 'input'/'evidence' trong
    few_shots - cac truong (question/reason/options) la CHINH bien cua
    `instructions`, nen loader phai tu render lai bang template do."""
    rp = loader.render("clarify_question", question="test", reason="test", options=[])
    user_contents = [m["content"] for m in rp.messages if m["role"] == "user"]
    assert any("Chiến dịch đó thế nào?" in c for c in user_contents)


def test_missing_context_variable_raises_clear_error(loader: PromptLoader) -> None:
    with pytest.raises(PromptValidationError):
        loader.render("narrate_campaign_diagnosis")  # thieu tone/max_words/sections


def test_render_raises_on_first_load_of_broken_yaml(tmp_path: Path) -> None:
    """Chua co ban nao trong cache -> khong co gi de "giu nguyen", phai bao loi."""
    (tmp_path / "broken.yaml").write_text("id: [\n  khong dong ngoac", encoding="utf-8")
    fresh_loader = PromptLoader(root=tmp_path)
    with pytest.raises(PromptValidationError):
        fresh_loader.get("broken")


def test_broken_yaml_on_reload_keeps_running_version(tmp_path: Path) -> None:
    """BAT BUOC: YAML hong -> GIU NGUYEN ban dang chay, khong raise."""
    prompt_path = tmp_path / "sample.yaml"
    prompt_path.write_text(
        "id: sample\nversion: \"1.0.0\"\nmodel_role: narrator\n"
        "system: |\n  he thong on dinh\n"
        "instructions: |\n  huong dan {{ topic }}\n",
        encoding="utf-8",
    )
    fresh_loader = PromptLoader(root=tmp_path)
    good = fresh_loader.get("sample")
    assert good["version"] == "1.0.0"

    # Gia lap thoi gian troi qua de mtime chac chan thay doi tren moi he thong file.
    import os
    import time

    time.sleep(0.05)
    prompt_path.write_text("id: [khong dong ngoac", encoding="utf-8")
    os.utime(prompt_path, None)

    still_good = fresh_loader.get("sample")
    assert still_good["version"] == "1.0.0"
    assert still_good == good


def test_reload_picks_up_valid_change(tmp_path: Path) -> None:
    prompt_path = tmp_path / "sample2.yaml"
    prompt_path.write_text(
        "id: sample2\nversion: \"1.0.0\"\nmodel_role: narrator\n"
        "system: |\n  ban dau\ninstructions: |\n  huong dan\n",
        encoding="utf-8",
    )
    fresh_loader = PromptLoader(root=tmp_path)
    v1 = fresh_loader.get("sample2")
    assert v1["version"] == "1.0.0"

    import time

    time.sleep(0.05)
    prompt_path.write_text(
        "id: sample2\nversion: \"1.1.0\"\nmodel_role: narrator\n"
        "system: |\n  da doi\ninstructions: |\n  huong dan\n",
        encoding="utf-8",
    )
    v2 = fresh_loader.get("sample2")
    assert v2["version"] == "1.1.0"


def test_render_version_matches_prompt_yaml(loader: PromptLoader) -> None:
    rp = loader.render(
        "route_intent", campaign_ids=["CMP-FB-001"], segments=["champion"],
    )
    assert rp.version == "1.0.0"
    assert rp.prompt_id == "route_intent"
