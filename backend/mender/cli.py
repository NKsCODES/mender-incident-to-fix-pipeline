"""mender serve | eval | demo | ingest"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from mender.config import ROOT, load_services, load_settings
from mender.db import Database
from mender.pipeline import Context, create_run, execute
from mender.runners import make_runner

CASES = str(ROOT / "fixtures" / "evals" / "cases.yaml")


def context(runner: str | None = None) -> Context:
    settings = load_settings()
    if runner:
        settings.runner = runner
    return Context(settings, Database(settings.db_path), load_services(settings.services_file), make_runner(settings))


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(prog="mender")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API and dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    ev = sub.add_parser("eval", help="run the eval suite; exits 1 if the gate fails")
    ev.add_argument("--runner", choices=["replay", "cursor"])
    ev.add_argument("--cases", default=CASES)
    demo = sub.add_parser("demo", help="process every fixture incident once so the dashboard has data")
    demo.add_argument("--mode", default="suggest")
    ing = sub.add_parser("ingest", help="run one incident JSON file through the pipeline")
    ing.add_argument("file")
    ing.add_argument("--mode", default=None)
    ing.add_argument("--runner", choices=["replay", "cursor"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if args.cmd == "serve":
        import uvicorn
        from mender.api import create_app
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    elif args.cmd == "eval":
        from mender.evals import run_eval
        out = run_eval(context(args.runner), args.cases)
        s = out["summary"]
        print(f"\neval {out['id']}  runner={out['runner']}  prompt={out['prompt_version']}")
        for c in out["cases"]:
            mark = {True: "ok ", False: "BAD", None: "   "}[c["matches_expected"]]
            print(f"  {mark} {c['case']:<26} {c['label']:<14} outcome={c['outcome']:<14} attempts={c['attempts']} {c['reason']}")
        print(f"\nresolve_rate={s['resolve_rate']}  false_fix_rate={s['false_fix_rate']}  labels={json.dumps(s['labels'])}")
        print("gate: PASS" if s["passed"] else "gate: FAIL\n  " + "\n  ".join(s["failures"]))
        sys.exit(0 if s["passed"] else 1)
    elif args.cmd == "demo":
        ctx = context("replay")
        for path in sorted((ROOT / "fixtures" / "incidents").glob("*.json")):
            run = execute(ctx, create_run(ctx.db, json.loads(path.read_text())), force_mode=args.mode)
            print(f"{path.stem:<26} {run['outcome']:<14} {run['reason']}")
    elif args.cmd == "ingest":
        ctx = context(args.runner)
        run = execute(ctx, create_run(ctx.db, json.loads(Path(args.file).read_text())), force_mode=args.mode)
        print(json.dumps({k: run[k] for k in ("id", "outcome", "reason", "attempts", "duration_ms", "tokens_in", "tokens_out", "cost_usd")}, indent=2))
        if run["diff"]:
            print(run["diff"])
