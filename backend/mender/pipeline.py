"""The incident to fix pipeline: gate, sandbox, triage, agent, verify, guardrails, publish."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from mender import guardrails, metrics, publisher, rollout, triage
from mender.config import ServiceConfig, Settings
from mender.db import Database, now
from mender.prompts import PROMPT_VERSION, build_prompt
from mender.runners import Runner
from mender.sandbox import Sandbox
from mender.tracing import Tracer
from mender.verify import verify

log = logging.getLogger("mender.pipeline")

SHIPPED = ("pr_draft", "pr_ready")
WOULD_SHIP = (*SHIPPED, "shadow_ok")


@dataclass
class Context:
    settings: Settings
    db: Database
    services: dict[str, ServiceConfig]
    runner: Runner


def cost_usd(settings: Settings, tokens_in: int | None, tokens_out: int | None) -> float | None:
    if tokens_in is None or tokens_out is None or not (settings.price_in or settings.price_out):
        return None
    return round(tokens_in / 1e6 * settings.price_in + tokens_out / 1e6 * settings.price_out, 6)


def execute(ctx: Context, run_id: str, force_mode: str | None = None) -> dict:
    """Runs one incident to completion. Never raises: every failure becomes a recorded outcome."""
    db = ctx.db
    run = db.get_run(run_id)
    incident = run["incident"]
    tracer = Tracer(db, run_id)
    started = now()
    db.update_run(run_id, status="running", runner=ctx.runner.name, prompt_version=PROMPT_VERSION)
    state: dict = {"outcome": "error", "reason": "", "mode": force_mode or "shadow"}
    tokens_in = tokens_out = None
    sb = None
    try:
        with tracer.span("pipeline", service=run["service"]):
            svc = ctx.services.get(run["service"])
            if svc is None:
                raise ValueError(f"service '{run['service']}' is not configured in mender.yaml")

            with tracer.span("gate") as sp:
                decision = rollout.Decision(True, force_mode, "forced") if force_mode else rollout.decide(db, svc, run["fingerprint"])
                sp.set(mode=decision.mode, reason=decision.reason, run=decision.run)
            state["mode"] = decision.mode
            if not decision.run:
                state.update(outcome="skipped", reason=decision.reason)
                return _finish(ctx, run_id, started, state, tokens_in, tokens_out)

            with tracer.span("sandbox"):
                sb = Sandbox(svc)
            with tracer.span("triage") as sp:
                context = triage.code_context(Path(sb.dir), incident)
                sp.set(frames=len(context), files=[c["filename"] for c in context])

            retry, agent_log, model = None, [], None
            for attempt in range(1, ctx.settings.max_attempts + 1):
                state["attempts"] = attempt
                with tracer.span("agent", attempt=attempt) as sp:
                    res = ctx.runner.run(
                        build_prompt(incident, context, retry), sb.dir, ctx.settings.agent_timeout_s,
                        {"event_id": incident.get("event_id"), "attempt": attempt, "run_id": run_id},
                    )
                    sp.set(ok=res.ok, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                           tool_calls=len(res.tool_calls), agent_ms=res.duration_ms, timed_out=res.timed_out)
                    if not res.ok:
                        sp.status = "error"
                model = res.model or model
                if res.tokens_in is not None:
                    tokens_in, tokens_out = (tokens_in or 0) + res.tokens_in, (tokens_out or 0) + (res.tokens_out or 0)
                    metrics.TOKENS.labels(kind="input").inc(res.tokens_in)
                    metrics.TOKENS.labels(kind="output").inc(res.tokens_out or 0)
                agent_log.append({"attempt": attempt, **{k: v for k, v in asdict(res).items() if k != "session_id"}})
                state.update(agent=agent_log, model=model)
                metrics.ATTEMPTS.labels(result="ok" if res.ok else ("timeout" if res.timed_out else "error")).inc()

                if not res.ok:
                    state.update(outcome="error", reason="agent_timeout" if res.timed_out else "agent_error", error=res.error)
                    break

                with tracer.span("diff") as sp:
                    changes, diff = sb.changes(), sb.diff()
                    sp.set(files=len(changes), lines=sum(c.added + c.deleted for c in changes))
                state["diff"] = diff
                if not changes:
                    state.update(outcome="no_fix", reason="agent made no changes")
                    break

                with tracer.span("verify", attempt=attempt) as sp:
                    v = verify(sb, changes, ctx.settings.test_timeout_s)
                    sp.set(repro=v["repro"], suite_passed=v["suite_passed"], new_tests=v["new_tests"])
                    if not v["suite_passed"]:
                        sp.status = "error"
                state["verify"] = v

                if not v["suite_passed"] or v["repro"] == "not_reproduced":
                    reason = "test suite fails with the patch" if not v["suite_passed"] else "the new test passes without the fix"
                    state.update(outcome="verify_failed", reason=reason)
                    if attempt < ctx.settings.max_attempts:
                        retry = {"reason": reason, "diff": diff, "output": v["suite_output"] or v["repro_output"]}
                        sb.reset()
                    continue

                with tracer.span("guardrails") as sp:
                    violations = guardrails.check(diff, changes, svc, v)
                    blocks = guardrails.blocking(violations)
                    sp.set(violations=[x["rule"] for x in violations])
                    if blocks:
                        sp.status = "error"
                state["guardrails"] = violations
                if blocks:
                    # No retry here: a patch that hid the error once is not trusted on a second try.
                    state.update(outcome="blocked", reason=", ".join(sorted({b["rule"] for b in blocks})))
                    break

                if decision.mode == "shadow":
                    state.update(outcome="shadow_ok", reason=decision.reason)
                    break
                with tracer.span("publish") as sp:
                    current = {**db.get_run(run_id), "attempts": attempt}
                    body = publisher.pr_body(current, res.text, v, violations)
                    pub = publisher.publish(sb, current, body, draft=decision.mode != "auto_pr", push=ctx.settings.publish)
                    sp.set(**pub)
                state.update(outcome="pr_ready" if decision.mode == "auto_pr" else "pr_draft", reason=decision.reason, pr_body=body, **pub)
                break
    except Exception as exc:  # noqa: BLE001 - the pipeline boundary: record, never crash the worker
        log.exception("run %s failed", run_id)
        state.update(outcome="error", reason="pipeline_exception", error=f"{type(exc).__name__}: {exc}"[:1000])
    finally:
        if sb is not None:
            sb.cleanup()
    return _finish(ctx, run_id, started, state, tokens_in, tokens_out)


def _finish(ctx: Context, run_id: str, started: float, state: dict, tokens_in, tokens_out) -> dict:
    cost = cost_usd(ctx.settings, tokens_in, tokens_out)
    if cost:
        metrics.COST.inc(cost)
    fields = {k: state.get(k) for k in ("outcome", "reason", "mode", "model", "diff", "verify", "guardrails", "agent", "error", "pr_body", "branch", "pr_url")}
    ctx.db.update_run(
        run_id, status="done", finished_at=now(), duration_ms=int((now() - started) * 1000),
        attempts=state.get("attempts", 0), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost, **fields,
    )
    run = ctx.db.get_run(run_id)
    metrics.RUNS.labels(service=run["service"], outcome=run["outcome"], mode=run["mode"] or "none").inc()
    log.info("run=%s service=%s outcome=%s reason=%s attempts=%s ms=%s", run_id, run["service"], run["outcome"], run["reason"], run["attempts"], run["duration_ms"])
    return run


def create_run(db: Database, incident: dict, eval_run_id: str | None = None) -> str:
    from mender.db import new_id

    run_id = new_id("run")
    db.insert(
        "runs", id=run_id, created_at=now(), service=incident["service"], fingerprint=triage.fingerprint(incident),
        title=triage.title(incident), status="queued", incident=incident,
        occurrences=int(incident.get("count") or 1), eval_run_id=eval_run_id,
    )
    return run_id
