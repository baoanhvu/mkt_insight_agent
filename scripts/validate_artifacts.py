"""Kiem tra tinh nhat quan cheo giua toan bo hien vat cau hinh.

Chay truoc moi commit va trong CI. Khong can database, khong can mang.

    python scripts/validate_artifacts.py

Exit code 0 = tat ca dat. Khac 0 = co loi, chi tiet in ra stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ERRORS: list[str] = []
WARNINGS: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)


def warn(msg: str) -> None:
    WARNINGS.append(msg)


def load(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        err(f"{path.relative_to(ROOT)}: khong parse duoc -> {exc}")
        return {}


def main() -> int:
    # -------------------------------------------------------------------------
    # 1. Nap
    # -------------------------------------------------------------------------
    entities = load(ROOT / "config/semantic/entities.yml")
    metrics_doc = load(ROOT / "config/semantic/metrics.yml")
    analytics = load(ROOT / "config/analytics.yaml")
    verify = load(ROOT / "config/verify.yaml")
    stages = load(ROOT / "config/stages.yaml")
    app_cfg = load(ROOT / "config/app.yaml")

    playbooks = {p.stem: load(p) for p in sorted((ROOT / "config/playbooks").glob("*.yml"))}
    prompts = {p.stem: load(p) for p in sorted((ROOT / "prompts").glob("*.yaml"))}
    golden = load(ROOT / "evals/golden/qa_set.yaml")

    for name in ["local", "greennode", "test"]:
        load(ROOT / f"config/profiles/{name}.yaml")
    load(ROOT / "config/secrets.example.yaml")

    metrics = metrics_doc.get("metrics", {})
    datasets = entities.get("datasets", {})
    dimensions = entities.get("dimensions", {})

    # -------------------------------------------------------------------------
    # 2. metrics.yml  <->  entities.yml
    # -------------------------------------------------------------------------
    for mname, m in metrics.items():
        if not isinstance(m, dict):
            err(f"metrics.{mname}: khong phai mapping")
            continue
        if "label_vi" not in m:
            err(f"metrics.{mname}: thieu label_vi")
        if "sql" not in m and "computed_by" not in m:
            err(f"metrics.{mname}: phai co `sql` hoac `computed_by`")
        ds = m.get("dataset")
        if ds and ds not in datasets:
            err(f"metrics.{mname}: dataset '{ds}' khong co trong entities.yml")
        for dim in m.get("allowed_dimensions", []) or []:
            if dim not in dimensions:
                err(f"metrics.{mname}: dimension '{dim}' khong co trong entities.yml")
        if m.get("unit") == "ratio" and m.get("min_sample_size") is None:
            warn(f"metrics.{mname}: chi so ty le nen co min_sample_size")

    for dname, d in dimensions.items():
        for ds in d.get("datasets", []) or []:
            if ds not in datasets:
                err(f"dimensions.{dname}: dataset '{ds}' khong ton tai")

    # -------------------------------------------------------------------------
    # 3. playbooks  ->  metrics / prompts / stages
    # -------------------------------------------------------------------------
    for pname, pb in playbooks.items():
        if pb.get("id") != pname:
            err(f"playbooks/{pname}.yml: id='{pb.get('id')}' khong khop ten file")
        prompt_id = pb.get("prompt")
        if prompt_id and prompt_id not in prompts:
            err(f"playbooks/{pname}: prompt '{prompt_id}' khong ton tai trong prompts/")
        for sec in pb.get("sections", []) or []:
            for mt in sec.get("metrics", []) or []:
                if mt not in metrics:
                    err(f"playbooks/{pname}.{sec.get('id')}: chi so '{mt}' khong co trong metrics.yml")
            for f in sec.get("filters", []) or []:
                dim = f.get("dimension")
                if dim and dim not in dimensions:
                    err(f"playbooks/{pname}.{sec.get('id')}: dimension '{dim}' khong ton tai")
            ob = sec.get("order_by")
            # Section lay tu thu vien hanh dong sap xep theo `priority`, khong theo chi so
            if sec.get("source") == "actions":
                ob = None
            if ob and ob not in metrics and ob not in dimensions:
                warn(f"playbooks/{pname}.{sec.get('id')}: order_by '{ob}' khong phai metric/dimension")
        for c in pb.get("required_caveats", []) or []:
            if "metric" in c and c["metric"] not in metrics:
                err(f"playbooks/{pname}: required_caveat tro toi chi so khong ton tai '{c['metric']}'")
            if "dimension" in c and c["dimension"] not in dimensions:
                err(f"playbooks/{pname}: required_caveat tro toi dimension khong ton tai '{c['dimension']}'")

    # Moi playbook phai co nhan giai doan trong stages.yaml
    overrides = stages.get("playbook_overrides", {})
    for pname in playbooks:
        if pname not in overrides:
            warn(f"stages.yaml: thieu playbook_overrides cho '{pname}'")

    # -------------------------------------------------------------------------
    # 4. prompts
    # -------------------------------------------------------------------------
    for pname, pr in prompts.items():
        if pr.get("id") != pname:
            err(f"prompts/{pname}.yaml: id='{pr.get('id')}' khong khop ten file")
        for field in ("version", "system", "instructions"):
            if field not in pr:
                err(f"prompts/{pname}: thieu truong '{field}'")
        if pr.get("renders_few_shots") is not False:
            warn(f"prompts/{pname}: nen dat renders_few_shots: false "
                 "(Jinja se nuot cac the {{...}} trong few_shots)")
        if pr.get("model_role") == "narrator":
            oc = pr.get("output_contract", {})
            pats = [p.get("pattern") for p in oc.get("forbidden_patterns", []) or []]
            if not any("d" in (p or "") for p in pats):
                warn(f"prompts/{pname}: narrator nen co forbidden_pattern chan chu so tran")

    # -------------------------------------------------------------------------
    # 5. verify.yaml
    # -------------------------------------------------------------------------
    w = verify.get("trust", {}).get("weights", {})
    if w:
        total = sum(w.values())
        if abs(total - 1.0) > 1e-6:
            err(f"verify.trust.weights: tong = {total}, phai bang 1.0")
    t_high = verify.get("trust", {}).get("t_high")
    t_low = verify.get("trust", {}).get("t_low")
    if t_high is not None and t_low is not None and not (0 < t_low < t_high < 1):
        err(f"verify.trust: can 0 < t_low({t_low}) < t_high({t_high}) < 1")
    if verify.get("calibrated") is True:
        warn("verify.calibrated = true: hay chac chan da chay evals/calibrate.py")
    if verify.get("numeric", {}).get("require_grounding_rate") != 1.0:
        err("verify.numeric.require_grounding_rate PHAI bang 1.0 (cong cung)")

    # -------------------------------------------------------------------------
    # 6. analytics.yaml
    # -------------------------------------------------------------------------
    seg = analytics.get("segmentation", {})
    rules = seg.get("rules", []) or []
    rule_ids = [r["id"] for r in rules]
    if rule_ids and rule_ids[0] != "high_risk":
        err("analytics.segmentation: luat dau tien phai la 'high_risk' "
            "(rui ro ghi de moi thuoc tinh khac)")
    validated = seg.get("validated", {})
    if validated:
        if validated.get("unclassified") != 0:
            err("analytics.segmentation.validated.unclassified phai bang 0")
        by_seg = validated.get("by_segment", {})
        total_n = sum(v["n"] for v in by_seg.values())
        if total_n != validated.get("total_customers"):
            err(f"analytics.segmentation: tong n = {total_n}, "
                f"khac total_customers = {validated.get('total_customers')}")
        for sid in by_seg:
            if sid not in rule_ids:
                err(f"analytics.segmentation.validated: phan khuc '{sid}' khong co luat tuong ung")

    seg_dim = dimensions.get("segment", {})
    for sid in rule_ids:
        if seg_dim and sid not in (seg_dim.get("allowed_values") or []):
            err(f"entities.dimensions.segment: thieu gia tri '{sid}'")

    for a in analytics.get("actions", []) or []:
        for field in ("id", "label_vi", "trigger", "target_metric",
                      "impact_formula", "impact_caveat_vi", "effort"):
            if field not in a:
                err(f"analytics.actions[{a.get('id', '?')}]: thieu truong bat buoc '{field}'")
        tm = a.get("target_metric")
        if tm and tm not in metrics:
            err(f"analytics.actions[{a.get('id')}]: target_metric '{tm}' khong co trong metrics.yml")

    # -------------------------------------------------------------------------
    # 7. golden set
    # -------------------------------------------------------------------------
    cases = golden.get("cases", []) or []
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        err("golden set: co id trung lap")
    if len(cases) < 100:
        warn(f"golden set: chi co {len(cases)} ca, khuyen nghi toi thieu 100")
    valid_intents = {
        "campaign_overview", "campaign_diagnosis", "funnel_analysis", "customer_persona",
        "segment_deep_dive", "clv_actions", "risk_fraud", "data_question",
        "freeform", "out_of_scope",
    }
    for c in cases:
        if c.get("expected_behavior") not in {"answer", "clarify", "refuse"}:
            err(f"golden.{c['id']}: expected_behavior khong hop le")
        ei = c.get("expected_intent")
        if ei and ei not in valid_intents:
            err(f"golden.{c['id']}: expected_intent '{ei}' khong hop le")
        if c.get("expected_behavior") == "refuse" and c.get("must_mention_numbers"):
            warn(f"golden.{c['id']}: ca refuse ma van yeu cau must_mention_numbers")

    n_trap = sum(1 for c in cases
                 if c.get("category") in {"adversarial", "unanswerable",
                                          "ambiguous", "empty_result"})
    if n_trap < 30:
        warn(f"golden set: chi {n_trap} ca bay, khuyen nghi >= 30")

    # Moi intent phai duoc phu it nhat mot ca
    covered = {c.get("expected_intent") for c in cases}
    for it in valid_intents:
        if it not in covered:
            warn(f"golden set: chua co ca nao cho intent '{it}'")

    # -------------------------------------------------------------------------
    # 8. app.yaml
    # -------------------------------------------------------------------------
    if app_cfg.get("app", {}).get("port") != 8080:
        err("app.yaml: AgentBase BAT BUOC cong 8080")
    if app_cfg.get("app", {}).get("host") != "0.0.0.0":
        err("app.yaml: phai lang nghe 0.0.0.0, khong phai 127.0.0.1")
    rpm = app_cfg.get("llm", {}).get("rate_limit", {}).get("requests_per_minute")
    if rpm and rpm >= 10:
        err(f"app.yaml: requests_per_minute = {rpm}, phai < 10 (tran MaaS)")
    ratio = app_cfg.get("ui", {}).get("chat_max_viewport_ratio")
    if ratio != 0.60:
        err(f"app.yaml: chat_max_viewport_ratio = {ratio}, yeu cau la 0.60")

    # -------------------------------------------------------------------------
    # 9. Python
    # -------------------------------------------------------------------------
    import py_compile
    for f in ["app/contracts.py", "app/errors.py"]:
        try:
            py_compile.compile(str(ROOT / f), doraise=True)
        except Exception as exc:  # noqa: BLE001
            err(f"{f}: khong compile duoc -> {exc}")

    # -------------------------------------------------------------------------
    # Ket qua
    # -------------------------------------------------------------------------
    print("=" * 74)
    print("KIEM TRA NHAT QUAN HIEN VAT")
    print("=" * 74)
    print(f"  dataset            {len(datasets)}")
    print(f"  dimension          {len(dimensions)}")
    print(f"  chi so             {len(metrics)}  (co reference: "
          f"{sum(1 for m in metrics.values() if isinstance(m, dict) and 'reference' in m)})")
    print(f"  playbook           {len(playbooks)}")
    print(f"  prompt             {len(prompts)}  (few-shot: "
          f"{sum(len(p.get('few_shots', []) or []) for p in prompts.values())})")
    print(f"  luat phan khuc     {len(rules)}")
    print(f"  hanh dong D3       {len(analytics.get('actions', []) or [])}")
    print(f"  ma loi             (xem app/errors.py)")
    print(f"  golden set         {len(cases)}  (ca bay: {n_trap})")
    print()

    for wmsg in WARNINGS:
        print(f"  CANH BAO  {wmsg}")
    if WARNINGS:
        print()
    for emsg in ERRORS:
        print(f"  LOI       {emsg}")

    print("=" * 74)
    if ERRORS:
        print(f"KET QUA: {len(ERRORS)} LOI, {len(WARNINGS)} canh bao")
        return 1
    print(f"KET QUA: DAT  ({len(WARNINGS)} canh bao)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
