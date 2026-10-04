"""Offline evals. Each case is a real captured incident plus a held-out test the agent never sees.

The headline number is the false-fix rate: patches the pipeline would have shipped that
do not actually satisfy the contract. Resolve rate without that number is vanity.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import yaml

from mender.db import new_id, now
from mender.pipeline import WOULD_SHIP, Context, create_run, execute
from mender.prompts import PROMPT_VERSION
from mender.sandbox import Sandbox

HELD_OUT_PATH = "tests/test_mender_heldout.py"


def heldout_passes(ctx: Context, run: dict, test_file: Path) -> bool | None:
    if not run.get("diff") or not test_file.is_file():
        return None
    sb = Sandbox(ctx.services[run["service"]])
    try:
        sb.apply_patch(run["diff"])
        (sb.dir / HELD_OUT_PATH).write_text(test_file.read_text())
        return sb.run_tests(ctx.settings.test_timeout_s, [HELD_OUT_PATH]).code == 0
    except RuntimeError:
        return False
    finally:
        sb.cleanup()


def classify(outcome: str, heldout: bool | None) -> str:
    if outcome in WOULD_SHIP:
        return "resolved" if heldout else "false_fix"
    if outcome == "blocked":
        return "over_block" if heldout else "correct_block"
    if outcome == "verify_failed":
        return "unresolved"
    return outcome  # no_fix, error


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, round(pct * (len(values) - 1)))]


def run_eval(ctx: Context, cases_file: str) -> dict:
    base = Path(cases_file).parent
    spec = yaml.safe_load(Path(cases_file).read_text())
    eval_id = new_id("eval")
    results = []
    for case in spec["cases"]:
        incident = json.loads((base / case["incident"]).read_text())
        run = execute(ctx, create_run(ctx.db, incident, eval_run_id=eval_id), force_mode="suggest")
        heldout = heldout_passes(ctx, run, base / case["heldout"]) if case.get("heldout") else None
        label = classify(run["outcome"], heldout)
        expected = case.get("expect") if ctx.runner.name == "replay" else None
        results.append({
            "case": case["id"], "run_id": run["id"], "outcome": run["outcome"], "reason": run["reason"],
            "heldout": heldout, "label": label, "expected": expected,
            "matches_expected": None if expected is None else expected == label,
            "attempts": run["attempts"], "duration_ms": run["duration_ms"],
            "tokens_in": run["tokens_in"], "tokens_out": run["tokens_out"], "cost_usd": run["cost_usd"],
        })

    count = lambda label: sum(1 for r in results if r["label"] == label)  # noqa: E731
    shipped = count("resolved") + count("false_fix")
    durations = [r["duration_ms"] for r in results if r["duration_ms"] is not None]
    costs = [r["cost_usd"] for r in results if r["cost_usd"] is not None]
    n = len(results)
    summary = {
        "cases": n,
        "labels": {k: count(k) for k in ("resolved", "false_fix", "correct_block", "over_block", "unresolved", "no_fix", "error")},
        "resolve_rate": round(count("resolved") / n, 3) if n else 0,
        "false_fix_rate": round(count("false_fix") / shipped, 3) if shipped else 0,
        "precision": round(count("resolved") / shipped, 3) if shipped else None,
        "p50_ms": statistics.median(durations) if durations else None,
        "p95_ms": percentile(durations, 0.95),
        "total_cost_usd": round(sum(costs), 4) if costs else None,
        "cost_per_resolved_usd": round(sum(costs) / count("resolved"), 4) if costs and count("resolved") else None,
    }
    gate = spec.get("gate", {})
    failures = []
    if ctx.runner.name == "replay":
        failures += [f"{r['case']}: expected {r['expected']}, got {r['label']}" for r in results if r["matches_expected"] is False]
    else:
        if summary["resolve_rate"] < gate.get("min_resolve_rate", 0):
            failures.append(f"resolve_rate {summary['resolve_rate']} below {gate['min_resolve_rate']}")
        if summary["false_fix_rate"] > gate.get("max_false_fix_rate", 1):
            failures.append(f"false_fix_rate {summary['false_fix_rate']} above {gate['max_false_fix_rate']}")
        if count("over_block") > gate.get("max_over_blocks", n):
            failures.append(f"{count('over_block')} over-blocks above {gate['max_over_blocks']}")
    summary.update(passed=not failures, failures=failures)
    ctx.db.insert("eval_runs", id=eval_id, created_at=now(), runner=ctx.runner.name, prompt_version=PROMPT_VERSION, summary=summary, cases=results)
    return {"id": eval_id, "runner": ctx.runner.name, "prompt_version": PROMPT_VERSION, "summary": summary, "cases": results}
