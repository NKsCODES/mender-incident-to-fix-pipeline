import hashlib
import hmac
import json
import time

from conftest import incident
from fastapi.testclient import TestClient

from mender import rollout
from mender.api import create_app
from mender.config import ROOT
from mender.evals import run_eval
from mender.pipeline import create_run, execute
from mender.runners.base import AgentResult


def run_case(ctx, name, mode="suggest"):
    return execute(ctx, create_run(ctx.db, incident(name)), force_mode=mode)


def test_good_fix_becomes_draft_pr_with_evidence(ctx):
    run = run_case(ctx, "pricing-zero-qty")
    assert run["outcome"] == "pr_draft" and run["branch"] == f"mender/{run['id']}"
    assert run["verify"]["repro"] == "reproduced" and run["verify"]["suite_passed"]
    assert "if quantity == 0" in run["diff"] and "Fails before the fix: reproduced" in run["pr_body"]
    assert run["tokens_in"] == 18400 and run["cost_usd"] == round(18400 / 1e6 * 3 + 620 / 1e6 * 15, 6)
    spans = {s["name"] for s in ctx.db.query("SELECT name FROM spans WHERE run_id=?", (run["id"],))}
    assert {"pipeline", "gate", "sandbox", "triage", "agent", "diff", "verify", "guardrails", "publish"} <= spans


def test_shadow_mode_never_publishes(ctx):
    run = run_case(ctx, "pricing-zero-qty", mode="shadow")
    assert run["outcome"] == "shadow_ok" and run["branch"] is None and run["pr_body"] is None


def test_auto_pr_mode(ctx):
    assert run_case(ctx, "currency-lowercase", mode="auto_pr")["outcome"] == "pr_ready"


def test_swallowed_exception_is_blocked(ctx):
    run = run_case(ctx, "inventory-unknown-sku")
    assert run["outcome"] == "blocked" and "broad_except" in run["reason"] and run["branch"] is None


def test_test_tampering_is_blocked(ctx):
    run = run_case(ctx, "cart-empty")
    assert run["outcome"] == "blocked" and "test_tampering" in run["reason"]


def test_failed_verification_retries_with_feedback(ctx):
    run = run_case(ctx, "tax-missing-region")
    assert run["outcome"] == "pr_draft" and run["attempts"] == 2
    assert run["tokens_in"] == 19100 + 23800
    assert '+    region = region or "EXPORT"' in run["diff"]  # the reverted first attempt left no trace


def test_no_change_is_no_fix_and_costs_are_still_recorded(ctx):
    run = run_case(ctx, "shipping-drone")
    assert run["outcome"] == "no_fix" and run["tokens_in"] == 14200


def test_agent_failure_and_unknown_service_become_recorded_errors(ctx):
    class Boom:
        name = "boom"

        def run(self, *a, **k):
            return AgentResult(ok=False, timed_out=True, error="agent exceeded 1s")

    ctx.runner = Boom()
    run = run_case(ctx, "pricing-zero-qty")
    assert (run["outcome"], run["reason"]) == ("error", "agent_timeout")
    inc = incident("pricing-zero-qty") | {"service": "nope"}
    run = execute(ctx, create_run(ctx.db, inc), force_mode="suggest")
    assert run["outcome"] == "error" and "not configured" in run["error"]


def test_retry_exhaustion_is_verify_failed(ctx):
    ctx.settings.max_attempts = 1
    assert run_case(ctx, "tax-missing-region")["outcome"] == "verify_failed"


def test_eval_suite_matches_expectations(ctx):
    out = run_eval(ctx, str(ROOT / "fixtures" / "evals" / "cases.yaml"))
    assert out["summary"]["passed"], out["summary"]["failures"]
    assert out["summary"]["labels"]["false_fix"] == 1  # the known harness blind spot stays visible


def wait_done(client, run_id):
    for _ in range(200):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] == "done":
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_api_end_to_end(settings):
    settings.webhook_secret = "s3cret"
    client = TestClient(create_app(settings))
    body = json.dumps(incident("currency-lowercase")).encode()
    assert client.post("/api/incidents", content=body).status_code == 401
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    headers = {"x-mender-signature": sig}

    first = client.post("/api/incidents", content=body, headers=headers).json()
    run = wait_done(client, first["run_id"])
    assert run["outcome"] == "shadow_ok" and run["mode"] == "shadow"  # new services default to shadow
    assert any(s["name"] == "agent" for s in run["spans"])

    again = client.post("/api/incidents", content=body, headers=headers).json()
    assert again == {"run_id": first["run_id"], "duplicate": True}
    assert client.get(f"/api/runs/{first['run_id']}").json()["occurrences"] == 87 * 2

    assert client.put("/api/rollout/checkout", json={"mode": "yolo"}).status_code == 422
    assert client.put("/api/rollout/checkout", json={"mode": "suggest", "sample_pct": 100}).json()["mode"] == "suggest"
    client.put("/api/rollout/kill-switch", json={"on": True})
    body2 = json.dumps(incident("pricing-zero-qty")).encode()
    sig2 = {"x-mender-signature": "sha256=" + hmac.new(b"s3cret", body2, hashlib.sha256).hexdigest()}
    skipped = wait_done(client, client.post("/api/incidents", content=body2, headers=sig2).json()["run_id"])
    assert skipped["outcome"] == "skipped"

    client.put("/api/rollout/kill-switch", json={"on": False})
    pr = wait_done(client, client.post("/api/incidents", content=body2, headers=sig2).json()["run_id"])
    assert pr["outcome"] == "pr_draft"  # a skipped run does not suppress the next occurrence
    assert client.post(f"/api/runs/{pr['id']}/feedback", json={"verdict": "accepted"}).json() == {"ok": True}

    stats = client.get("/api/stats").json()
    assert stats["prs_opened"] == 1 and stats["accept_rate"] == 1.0 and stats["outcomes"]["skipped"] == 1
    assert "mender_runs_total" in client.get("/metrics").text
    assert client.get("/healthz").json()["ok"]
    assert client.post("/api/incidents", content=b'{"service":"checkout"}', headers={"x-mender-signature": "sha256=" + hmac.new(b"s3cret", b'{"service":"checkout"}', hashlib.sha256).hexdigest()}).status_code == 422


def test_restart_marks_interrupted_runs(settings, ctx):
    run_id = create_run(ctx.db, incident("pricing-zero-qty"))
    ctx.db.update_run(run_id, status="running")
    create_app(settings)
    run = ctx.db.get_run(run_id)
    assert (run["status"], run["reason"]) == ("done", "interrupted_by_restart")
    assert rollout.get_policy(ctx.db, ctx.services["checkout"])["mode"] == "shadow"
