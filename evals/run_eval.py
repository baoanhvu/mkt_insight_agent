"""Chay bo cau hoi vang (evals/golden/qa_set.yaml) qua Orchestrator that va
tinh cac chi so o docs/13-testing-eval.md muc 13.5.

CHI mot phan cac chi so trong bang 13.5 duoc trien khai day du o day:

    numeric_grounding_rate, entity_grounding_rate, must_mention_recall,
    must_not_mention_violations, refusal_accuracy, false_refusal_rate,
    avg_trust_score, llm_calls_per_answer, p95_latency_ms

`execution_accuracy` la MOT PHIEN BAN DON GIAN HOA (# ASSUMPTION): duong hoi
tu do (freeform, agent tu sinh SQL) chua ton tai (do la T12), nen khong co
"SQL cua agent" de doi chieu voi `gold_sql` theo dung nghia cua tai lieu. O
day thay bang: chay `gold_sql` qua engine read-only, roi kiem tra CAC GIA TRI
VO HUONG cua ket qua co xuat hien (dung dinh dang vi-VN) trong cau tra loi
cuoi cung hay khong - xap xi hop ly cho kien truc "code tinh, LLM chi dien
giai" hien tai, nhung se can viet lai khi T12 xong.

`--seeds`/hieu chinh nguong bang hoi quy logistic (docs 13.6) la viec cua
`evals/calibrate.py` rieng, KHONG thuoc pham vi lenh nghiem thu T09. Voi
provider mock (profile=test), moi lan chay deterministic (khong co temperature
thuc), nen --seeds > 1 chi lap lai cung ket qua - da ghi ASSUMPTION o cho dung.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GOLDEN_PATH = Path(__file__).parent / "golden" / "qa_set.yaml"
BASELINE_PATH = Path(__file__).parent / ".baseline.json"

_ANSWERED_DECISIONS = {"ANSWERED", "HEDGED"}
_REFUSED_DECISIONS = {"ABSTAINED", "BLOCKED"}


@dataclass(slots=True)
class QaCase:
    id: str
    question: str
    category: str
    difficulty: str
    split: str
    expected_behavior: str
    expected_intent: str | None = None
    gold_sql: str | None = None
    must_mention_numbers: list[str] = field(default_factory=list)
    must_mention_entities: list[str] = field(default_factory=list)
    must_mention_phrases: list[str] = field(default_factory=list)
    must_not_mention_numbers: list[str] = field(default_factory=list)
    must_not_mention_entities: list[str] = field(default_factory=list)
    must_not_mention_phrases: list[str] = field(default_factory=list)
    expected_stats_flag: dict[str, Any] | None = None
    expected_artifact: dict[str, Any] | None = None
    notes: str = ""


@dataclass(slots=True)
class CaseResult:
    case: QaCase
    decision: str
    trust_value: float | None
    llm_calls: int
    latency_ms: float
    narrative: str
    numeric_score: float | None
    entity_score: float | None
    mention_hits: int
    mention_total: int
    violations: list[str]
    execution_match: bool | None
    error: str | None = None


def load_qa_cases(path: Path = GOLDEN_PATH) -> list[QaCase]:
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases: list[QaCase] = []
    for c in raw["cases"]:
        cases.append(QaCase(
            id=c["id"], question=c["question"], category=c["category"],
            difficulty=c["difficulty"], split=c["split"],
            expected_behavior=c["expected_behavior"],
            expected_intent=c.get("expected_intent"), gold_sql=c.get("gold_sql"),
            must_mention_numbers=list(c.get("must_mention_numbers") or []),
            must_mention_entities=list(c.get("must_mention_entities") or []),
            must_mention_phrases=list(c.get("must_mention_phrases") or []),
            must_not_mention_numbers=list(c.get("must_not_mention_numbers") or []),
            must_not_mention_entities=list(c.get("must_not_mention_entities") or []),
            must_not_mention_phrases=list(c.get("must_not_mention_phrases") or []),
            expected_stats_flag=c.get("expected_stats_flag"),
            expected_artifact=c.get("expected_artifact"),
            notes=c.get("notes", ""),
        ))
    return cases


def select_cases(cases: list[QaCase], *, split: str, quick: bool) -> list[QaCase]:
    if split != "all":
        cases = [c for c in cases if c.split == split]
    if quick:
        cases = cases[:20]
    return cases


def _has_bare_number(text: str) -> bool:
    from app.verify.config import get_verify_config
    from app.verify.vi_text import find_bare_numbers
    cfg = get_verify_config()
    return len(find_bare_numbers(text, tuple(cfg.unit_aliases))) > 0


def _check_violations(narrative: str, case: QaCase) -> list[str]:
    violations: list[str] = []
    for n in case.must_not_mention_numbers:
        if n == "*":
            if _has_bare_number(narrative):
                violations.append(f"so tran khong duoc phep xuat hien nhung co: {case.id}")
        elif n in narrative:
            violations.append(f"so cam '{n}' xuat hien trong: {case.id}")
    for e in case.must_not_mention_entities:
        if e in narrative:
            violations.append(f"thuc the cam '{e}' xuat hien trong: {case.id}")
    for p in case.must_not_mention_phrases:
        if p in narrative:
            violations.append(f"cum tu cam '{p}' xuat hien trong: {case.id}")
    return violations


def _check_mentions(narrative: str, case: QaCase) -> tuple[int, int]:
    required = case.must_mention_numbers + case.must_mention_entities + case.must_mention_phrases
    hits = sum(1 for item in required if item in narrative)
    return hits, len(required)


def _try_execution_match(case: QaCase, narrative: str) -> bool | None:
    if not case.gold_sql:
        return None
    try:
        from sqlalchemy import text as sql_text

        from app.data.engines import get_engine_ro
        from app.web.formatting import fmt_count

        engine = get_engine_ro()
        with engine.connect() as conn:
            rows = conn.execute(sql_text(case.gold_sql)).fetchall()
        scalars = [v for row in rows for v in row if isinstance(v, int | float)]
        if not scalars:
            return None
        return any(fmt_count(float(v)) in narrative for v in scalars)
    except Exception:
        return None


async def run_case(orchestrator: Any, case: QaCase) -> CaseResult:
    from app.verify.numeric import check_numeric_grounding

    started = time.perf_counter()
    try:
        state = await orchestrator.answer(case.question)
    except Exception as exc:  # ca nghiem trong - ghi lai, khong lam sap ca chay
        return CaseResult(
            case=case, decision="ERROR", trust_value=None, llm_calls=0,
            latency_ms=(time.perf_counter() - started) * 1000, narrative="",
            numeric_score=None, entity_score=None, mention_hits=0, mention_total=0,
            violations=[], execution_match=None, error=repr(exc),
        )
    latency_ms = (time.perf_counter() - started) * 1000

    narrative = state.narrative_final or ""
    numeric_score: float | None = None
    entity_score: float | None = None
    if state.trust is not None:
        numeric_check = state.trust.components.get("numeric_grounding")
        entity_check = state.trust.components.get("entity_grounding")
        numeric_score = numeric_check.score if numeric_check else None
        entity_score = entity_check.score if entity_check else None
    elif state.narrative_template and state.evidence is not None:
        # Nhanh HET LUOT GOI LLM (bang tho, khong qua verify) - tu tinh rieng
        # de khong bo sot ca nay khoi numeric_grounding_rate.
        numeric_score = check_numeric_grounding(state.narrative_template, state.evidence).score

    hits, total = _check_mentions(narrative, case)
    violations = _check_violations(narrative, case)
    execution_match = _try_execution_match(case, narrative) if state.decision.value in _ANSWERED_DECISIONS else None

    return CaseResult(
        case=case, decision=state.decision.value, trust_value=state.trust.value if state.trust else None,
        llm_calls=state.llm_calls, latency_ms=latency_ms, narrative=narrative,
        numeric_score=numeric_score, entity_score=entity_score,
        mention_hits=hits, mention_total=total, violations=violations,
        execution_match=execution_match,
    )


@dataclass(slots=True)
class EvalReport:
    results: list[CaseResult]
    metrics: dict[str, float | int | None]


def aggregate(results: list[CaseResult]) -> EvalReport:
    answered = [r for r in results if r.decision in _ANSWERED_DECISIONS]
    refuse_expected = [r for r in results if r.case.expected_behavior in ("refuse", "clarify")]
    answer_expected = [r for r in results if r.case.expected_behavior == "answer"]

    numeric_scores = [r.numeric_score for r in answered if r.numeric_score is not None]
    entity_scores = [r.entity_score for r in answered if r.entity_score is not None]
    trust_values = [r.trust_value for r in results if r.trust_value is not None]
    total_hits = sum(r.mention_hits for r in results)
    total_mentions = sum(r.mention_total for r in results)
    total_violations = sum(len(r.violations) for r in results)
    latencies = sorted(r.latency_ms for r in results)
    exec_matches = [r.execution_match for r in results if r.execution_match is not None]

    def _p95(xs: list[float]) -> float | None:
        if not xs:
            return None
        idx = min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))
        return xs[idx]

    def _rate(hits: int, denom: int) -> float | None:
        return hits / denom if denom else None

    metrics: dict[str, float | int | None] = {
        "n_cases": len(results),
        "numeric_grounding_rate": statistics.mean(numeric_scores) if numeric_scores else 1.0,
        "entity_grounding_rate": statistics.mean(entity_scores) if entity_scores else 1.0,
        "must_mention_recall": _rate(total_hits, total_mentions),
        "must_not_mention_violations": total_violations,
        "refusal_accuracy": _rate(
            sum(1 for r in refuse_expected if r.decision in _REFUSED_DECISIONS), len(refuse_expected),
        ),
        "false_refusal_rate": _rate(
            sum(1 for r in answer_expected if r.decision in _REFUSED_DECISIONS), len(answer_expected),
        ),
        "avg_trust_score": statistics.mean(trust_values) if trust_values else None,
        "llm_calls_per_answer": statistics.mean(r.llm_calls for r in results) if results else None,
        "p95_latency_ms": _p95(latencies),
        "execution_accuracy": _rate(sum(1 for m in exec_matches if m), len(exec_matches)),
        "n_errors": sum(1 for r in results if r.decision == "ERROR"),
    }
    return EvalReport(results=results, metrics=metrics)


def print_text_report(report: EvalReport) -> None:
    m = report.metrics
    print(f"=== evals.run_eval - {m['n_cases']} ca ===")
    print(f"numeric_grounding_rate      = {m['numeric_grounding_rate']:.3f}  (cong cung: == 1.000)")
    print(f"must_not_mention_violations = {m['must_not_mention_violations']}  (cong cung: == 0)")
    print(f"entity_grounding_rate       = {m['entity_grounding_rate']:.3f}")
    if m["must_mention_recall"] is not None:
        print(f"must_mention_recall         = {m['must_mention_recall']:.3f}")
    if m["refusal_accuracy"] is not None:
        print(f"refusal_accuracy            = {m['refusal_accuracy']:.3f}")
    if m["false_refusal_rate"] is not None:
        print(f"false_refusal_rate          = {m['false_refusal_rate']:.3f}")
    if m["avg_trust_score"] is not None:
        print(f"avg_trust_score              = {m['avg_trust_score']:.3f}")
    if m["llm_calls_per_answer"] is not None:
        print(f"llm_calls_per_answer         = {m['llm_calls_per_answer']:.2f}")
    if m["p95_latency_ms"] is not None:
        print(f"p95_latency_ms               = {m['p95_latency_ms']:.0f}")
    if m["execution_accuracy"] is not None:
        print(f"execution_accuracy (xap xi)  = {m['execution_accuracy']:.3f}")
    if m["n_errors"]:
        print(f"!! n_errors = {m['n_errors']} - xem chi tiet ben duoi")

    failed = [r for r in report.results if r.violations or r.decision == "ERROR"]
    if failed:
        print("\n--- Ca can chu y ---")
        for r in failed:
            tag = r.error or "; ".join(r.violations)
            print(f"  [{r.case.id}] {r.case.category}: {tag}")


def write_html_report(report: EvalReport, path: Path) -> None:
    m = report.metrics
    rows = "".join(
        f"<tr><td>{r.case.id}</td><td>{r.case.category}</td><td>{r.case.difficulty}</td>"
        f"<td>{r.case.expected_behavior}</td><td>{r.decision}</td>"
        f"<td>{'' if r.trust_value is None else f'{r.trust_value:.2f}'}</td>"
        f"<td>{len(r.violations)}</td></tr>"
        for r in report.results
    )
    html = f"""<!doctype html><meta charset="utf-8">
<title>evals.run_eval</title>
<style>body{{font-family:sans-serif}}table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px 8px}}</style>
<h1>evals.run_eval</h1>
<p>numeric_grounding_rate = {m['numeric_grounding_rate']:.3f} &middot;
must_not_mention_violations = {m['must_not_mention_violations']}</p>
<table><tr><th>id</th><th>category</th><th>difficulty</th><th>expected</th>
<th>decision</th><th>trust</th><th>violations</th></tr>{rows}</table>"""
    path.write_text(html, encoding="utf-8")


def _load_baseline() -> dict[str, Any] | None:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return None


def _save_baseline(metrics: dict[str, Any]) -> None:
    BASELINE_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def _check_regression(metrics: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    prev_exec = baseline.get("execution_accuracy")
    cur_exec = metrics.get("execution_accuracy")
    if prev_exec is not None and cur_exec is not None and cur_exec < prev_exec - 0.03:
        problems.append(
            f"execution_accuracy tut {prev_exec:.3f} -> {cur_exec:.3f} (qua 3 diem %)",
        )
    return problems


async def _run_all(cases: list[QaCase]) -> list[CaseResult]:
    from app.agent.orchestrator import build_orchestrator

    orchestrator = build_orchestrator()
    return [await run_case(orchestrator, c) for c in cases]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chay golden set qua Orchestrator that.")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--profile", choices=["local", "greennode", "test"], default="test")
    parser.add_argument("--quick", action="store_true", help="chi 20 ca dau")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--report", choices=["text", "html"], default="text")
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--save-baseline", action="store_true")
    args = parser.parse_args(argv)

    # PHAI dat truoc khi import bat ky module app.* nao (get_settings() cache
    # lru theo tien trinh - xem app/settings.py).
    os.environ["APP_PROFILE"] = args.profile

    import asyncio

    all_cases = load_qa_cases()
    cases = select_cases(all_cases, split=args.split, quick=args.quick)
    if not cases:
        print(f"Khong co ca nao khop split='{args.split}'.", file=sys.stderr)
        return 1

    # ASSUMPTION: provider mock (profile=test) tra loi deterministic (khong
    # co temperature thuc), nen cac seed lap lai cho ra CUNG ket qua - chi
    # thuc su can lap seed khi profile la local/greennode (LLM that).
    seed_reports = []
    for _ in range(max(1, args.seeds)):
        results = asyncio.run(_run_all(cases))
        seed_reports.append(aggregate(results))

    report = seed_reports[0]
    if len(seed_reports) > 1:
        keys = report.metrics.keys()
        for k in keys:
            vals = [r.metrics[k] for r in seed_reports if r.metrics[k] is not None]
            if vals and all(isinstance(v, int | float) for v in vals):
                mean = statistics.mean(vals)
                stdev = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                print(f"{k}: {mean:.3f} +/- {stdev:.3f} (tren {len(seed_reports)} seed)")

    print_text_report(report)
    if args.report == "html":
        out_path = Path("evals") / "report.html"
        write_html_report(report, out_path)
        print(f"\nBao cao HTML: {out_path}")

    exit_code = 0
    if report.metrics["numeric_grounding_rate"] != 1.0:
        print("\nCHAN: numeric_grounding_rate < 1.000 - cong cung, khong co ngoai le.", file=sys.stderr)
        exit_code = 1
    if report.metrics["must_not_mention_violations"]:
        print("CHAN: must_not_mention_violations > 0 - cong cung.", file=sys.stderr)
        exit_code = 1

    if args.fail_on_regression:
        baseline = _load_baseline()
        if baseline is not None:
            problems = _check_regression(report.metrics, baseline)
            for p in problems:
                print(f"CHAN (regression): {p}", file=sys.stderr)
            if problems:
                exit_code = 1
    if args.save_baseline:
        _save_baseline(report.metrics)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
