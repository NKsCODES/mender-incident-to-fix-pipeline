import copy

from conftest import incident
from mender import rollout, triage
from mender.config import ROOT
from mender.db import new_id, now


def test_fingerprint_ignores_line_numbers_and_literals():
    a = incident("coupon-percent-sign")
    b = copy.deepcopy(a)
    b["exception"]["frames"][-1]["lineno"] += 40
    b["exception"]["value"] = b["exception"]["value"].replace("10%", "25%")
    assert triage.fingerprint(a) == triage.fingerprint(b)
    assert triage.fingerprint(a) != triage.fingerprint(incident("pricing-zero-qty"))


def test_code_context_marks_failing_line():
    ctx = triage.code_context(ROOT / "fixtures" / "target-repo", incident("pricing-zero-qty"))
    assert ctx[0]["filename"] == "checkout/pricing.py"
    assert ">>" in ctx[0]["snippet"] and "total_cents // quantity" in ctx[0]["snippet"]


def test_code_context_refuses_paths_outside_repo():
    inc = incident("pricing-zero-qty")
    inc["exception"]["frames"] = [{"filename": "../../../../etc/passwd", "lineno": 1, "function": "x"},
                                  {"filename": "/etc/passwd", "lineno": 1, "function": "x"}]
    assert triage.code_context(ROOT / "fixtures" / "target-repo", inc) == []


def seed(db, outcome, feedback=None, n=1):
    for _ in range(n):
        db.insert("runs", id=new_id("run"), created_at=now(), service="checkout", status="done", outcome=outcome, feedback=feedback)


def test_default_is_shadow_and_kill_switch_wins(ctx):
    svc = ctx.services["checkout"]
    assert rollout.decide(ctx.db, svc, "00000000").mode == "shadow"
    rollout.set_policy(ctx.db, "checkout", "auto_pr", 100)
    assert rollout.decide(ctx.db, svc, "00000000").mode == "auto_pr"
    ctx.db.set_setting("kill_switch", "on")
    d = rollout.decide(ctx.db, svc, "00000000")
    assert not d.run and "kill switch" in d.reason


def test_sampling_is_deterministic(ctx):
    svc = ctx.services["checkout"]
    rollout.set_policy(ctx.db, "checkout", "suggest", 25)
    assert rollout.decide(ctx.db, svc, f"{10:08x}").run       # 10 < 25
    assert not rollout.decide(ctx.db, svc, f"{60:08x}").run   # 60 >= 25
    rollout.set_policy(ctx.db, "checkout", "suggest", 0)
    assert not rollout.decide(ctx.db, svc, f"{0:08x}").run


def test_breaker_opens_on_rejections_not_on_blocks(ctx):
    svc = ctx.services["checkout"]
    rollout.set_policy(ctx.db, "checkout", "suggest", 100)
    seed(ctx.db, "blocked", n=8)
    assert not rollout.breaker(ctx.db, "checkout")["open"]
    seed(ctx.db, "pr_draft", feedback="rejected", n=6)
    assert rollout.breaker(ctx.db, "checkout")["open"]
    d = rollout.decide(ctx.db, svc, "00000000")
    assert d.run and d.mode == "shadow"
