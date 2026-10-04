"""HTTP API: incident webhook, run inspection, rollout controls, evals, metrics. Also serves the dashboard."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from mender import evals, metrics, rollout
from mender.config import ROOT, Settings, load_services, load_settings
from mender.db import Database, now
from mender.evals import percentile
from mender.pipeline import SHIPPED, WOULD_SHIP, Context, create_run, execute
from mender.runners import make_runner

LIST_COLS = "id, created_at, finished_at, service, title, status, outcome, reason, mode, runner, attempts, tokens_in, tokens_out, cost_usd, duration_ms, occurrences, feedback, eval_run_id"


class Frame(BaseModel):
    filename: str = Field(max_length=400)
    lineno: int = Field(ge=0, le=10_000_000)
    function: str = Field(default="", max_length=200)
    context_line: str = Field(default="", max_length=500)
    in_app: bool = True


class ExceptionIn(BaseModel):
    type: str = Field(max_length=200)
    value: str = Field(default="", max_length=2000)
    frames: list[Frame] = Field(default_factory=list, max_length=100)


class IncidentIn(BaseModel):
    service: str = Field(max_length=100)
    exception: ExceptionIn
    event_id: str | None = Field(default=None, max_length=100)
    environment: str = Field(default="production", max_length=50)
    release: str | None = Field(default=None, max_length=100)
    request: dict | None = None
    count: int = Field(default=1, ge=1)


class PolicyIn(BaseModel):
    mode: str
    sample_pct: int = 100


class KillIn(BaseModel):
    on: bool


class FeedbackIn(BaseModel):
    verdict: str  # accepted | rejected
    note: str = Field(default="", max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db = Database(settings.db_path)
    ctx = Context(settings, db, load_services(settings.services_file), make_runner(settings))
    pool = ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="mender")
    app = FastAPI(title="Mender", version="0.1.0")
    app.state.ctx, app.state.pool = ctx, pool

    # Runs left mid-flight by a crash or deploy would otherwise sit "running" forever.
    for row in db.query("SELECT id FROM runs WHERE status IN ('queued','running')"):
        db.update_run(row["id"], status="done", outcome="error", reason="interrupted_by_restart", finished_at=now())

    @app.get("/healthz")
    def healthz():
        db.one("SELECT 1 AS ok")
        return {"ok": True, "runner": ctx.runner.name, "services": list(ctx.services)}

    @app.get("/metrics")
    def prom():
        depth = db.one("SELECT COUNT(*) AS n FROM runs WHERE status IN ('queued','running')")["n"]
        metrics.QUEUE_DEPTH.set(depth)
        return Response(generate_latest(metrics.REGISTRY), media_type=CONTENT_TYPE_LATEST)

    @app.post("/api/incidents", status_code=202)
    async def ingest(request: Request):
        raw = await request.body()
        if settings.webhook_secret:
            expected = "sha256=" + hmac.new(settings.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, request.headers.get("x-mender-signature", "")):
                raise HTTPException(401, "bad signature")
        try:
            incident = IncidentIn.model_validate_json(raw).model_dump()
        except ValueError as exc:
            raise HTTPException(422, str(exc)[:500]) from exc
        if incident["service"] not in ctx.services:
            raise HTTPException(404, f"unknown service '{incident['service']}'")

        from mender.triage import fingerprint
        fp = fingerprint(incident)
        dup = db.one(
            "SELECT id, occurrences FROM runs WHERE fingerprint=? AND eval_run_id IS NULL AND created_at>? "
            "AND (status!='done' OR outcome NOT IN ('error','skipped')) ORDER BY created_at DESC LIMIT 1",
            (fp, now() - settings.dedupe_hours * 3600),
        )
        if dup:
            db.update_run(dup["id"], occurrences=dup["occurrences"] + incident["count"])
            metrics.DUPLICATES.labels(service=incident["service"]).inc()
            return {"run_id": dup["id"], "duplicate": True}
        run_id = create_run(db, incident)
        pool.submit(execute, ctx, run_id)
        return {"run_id": run_id, "duplicate": False}

    @app.get("/api/runs")
    def list_runs(limit: int = 100, include_evals: bool = False):
        where = "" if include_evals else "WHERE eval_run_id IS NULL"
        return db.query(f"SELECT {LIST_COLS} FROM runs {where} ORDER BY created_at DESC LIMIT ?", (min(limit, 500),))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = db.get_run(run_id)
        if not run:
            raise HTTPException(404, "run not found")
        run["spans"] = db.query("SELECT * FROM spans WHERE run_id=? ORDER BY start_ms", (run_id,))
        return run

    @app.post("/api/runs/{run_id}/feedback")
    def feedback(run_id: str, body: FeedbackIn):
        if body.verdict not in ("accepted", "rejected"):
            raise HTTPException(422, "verdict must be accepted or rejected")
        if not db.get_run(run_id):
            raise HTTPException(404, "run not found")
        db.update_run(run_id, feedback=body.verdict, feedback_note=body.note)
        return {"ok": True}

    @app.get("/api/stats")
    def stats():
        runs = db.query(f"SELECT {LIST_COLS}, guardrails FROM runs WHERE eval_run_id IS NULL AND status='done'")
        outcomes: dict[str, int] = {}
        rules: dict[str, int] = {}
        for r in runs:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            for v in r["guardrails"] or []:
                rules[v["rule"]] = rules.get(v["rule"], 0) + 1
        attempted = [r for r in runs if r["outcome"] != "skipped"]
        ok = [r for r in attempted if r["outcome"] in WOULD_SHIP]
        reviewed = [r for r in runs if r["feedback"]]
        costs = [r["cost_usd"] for r in attempted if r["cost_usd"] is not None]
        stages = {}
        for name in ("sandbox", "triage", "agent", "verify", "guardrails", "publish"):
            d = [s["end_ms"] - s["start_ms"] for s in db.query(
                "SELECT s.start_ms, s.end_ms FROM spans s JOIN runs r ON r.id=s.run_id WHERE s.name=? AND r.eval_run_id IS NULL", (name,))]
            stages[name] = {"count": len(d), "p50_ms": percentile(d, 0.5), "p95_ms": percentile(d, 0.95)}
        durations = [r["duration_ms"] for r in ok if r["duration_ms"] is not None]
        return {
            "runs": len(runs), "attempted": len(attempted), "outcomes": outcomes, "guardrail_rules": rules,
            "fix_rate": round(len(ok) / len(attempted), 3) if attempted else None,
            "prs_opened": sum(1 for r in runs if r["outcome"] in SHIPPED),
            "accept_rate": round(sum(1 for r in reviewed if r["feedback"] == "accepted") / len(reviewed), 3) if reviewed else None,
            "reviewed": len(reviewed),
            "occurrences_covered": sum(r["occurrences"] for r in ok),
            "p50_time_to_fix_ms": percentile(durations, 0.5), "p95_time_to_fix_ms": percentile(durations, 0.95),
            "tokens_in": sum(r["tokens_in"] or 0 for r in runs), "tokens_out": sum(r["tokens_out"] or 0 for r in runs),
            "cost_usd": round(sum(costs), 4) if costs else None,
            "cost_per_fix_usd": round(sum(costs) / len(ok), 4) if costs and ok else None,
            "stages": stages,
        }

    @app.get("/api/rollout")
    def get_rollout():
        return {
            "kill_switch": db.get_setting("kill_switch", "off") == "on",
            "modes": rollout.MODES,
            "services": [{**rollout.get_policy(db, svc), "breaker": rollout.breaker(db, name)} for name, svc in ctx.services.items()],
        }

    @app.put("/api/rollout/kill-switch")
    def kill(body: KillIn):
        db.set_setting("kill_switch", "on" if body.on else "off")
        return {"kill_switch": body.on}

    @app.put("/api/rollout/{service}")
    def put_policy(service: str, body: PolicyIn):
        if service not in ctx.services:
            raise HTTPException(404, "unknown service")
        try:
            rollout.set_policy(db, service, body.mode, body.sample_pct)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return rollout.get_policy(db, ctx.services[service])

    @app.get("/api/evals")
    def list_evals():
        return db.query("SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT 30")

    @app.post("/api/evals/run", status_code=202)
    def start_eval():
        pool.submit(evals.run_eval, ctx, str(ROOT / "fixtures" / "evals" / "cases.yaml"))
        return {"started": True}

    dist = Path(settings.dashboard_dir)
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            return FileResponse(dist / "index.html")

    return app
