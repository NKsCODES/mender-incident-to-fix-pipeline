"""Rollout control: kill switch, per-service mode, deterministic sampling and a circuit breaker.

Modes, in order of trust:
  off      incidents are ignored
  shadow   full pipeline runs and is recorded, nothing leaves the system
  suggest  a draft PR is opened for a human
  auto_pr  a ready-for-review PR is opened
"""
from __future__ import annotations

from dataclasses import dataclass

from mender import metrics
from mender.config import ServiceConfig
from mender.db import Database

MODES = ("off", "shadow", "suggest", "auto_pr")
BREAKER_WINDOW, BREAKER_MIN, BREAKER_RATIO = 10, 5, 0.5


@dataclass
class Decision:
    run: bool
    mode: str
    reason: str


def get_policy(db: Database, svc: ServiceConfig) -> dict:
    row = db.one("SELECT * FROM policies WHERE service=?", (svc.name,))
    return row or {"service": svc.name, "mode": svc.default_mode, "sample_pct": 100}


def set_policy(db: Database, service: str, mode: str, sample_pct: int):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not 0 <= sample_pct <= 100:
        raise ValueError("sample_pct must be within 0..100")
    db.insert("policies", service=service, mode=mode, sample_pct=sample_pct)


def breaker(db: Database, service: str) -> dict:
    """Opens when recent runs keep erroring or humans keep rejecting the PRs.
    Guardrail blocks do not count: a block is the system working."""
    rows = db.query(
        "SELECT outcome, feedback FROM runs WHERE service=? AND status='done' AND eval_run_id IS NULL "
        "AND outcome NOT IN ('skipped') ORDER BY created_at DESC LIMIT ?",
        (service, BREAKER_WINDOW),
    )
    bad = sum(1 for r in rows if r["outcome"] == "error" or r["feedback"] == "rejected")
    is_open = len(rows) >= BREAKER_MIN and bad / len(rows) >= BREAKER_RATIO
    metrics.BREAKER_OPEN.labels(service=service).set(1 if is_open else 0)
    return {"open": is_open, "bad": bad, "window": len(rows)}


def decide(db: Database, svc: ServiceConfig, fingerprint: str) -> Decision:
    if db.get_setting("kill_switch", "off") == "on":
        return Decision(False, "off", "kill switch is on")
    policy = get_policy(db, svc)
    if policy["mode"] == "off":
        return Decision(False, "off", "service mode is off")
    if int(fingerprint[:8], 16) % 100 >= policy["sample_pct"]:
        return Decision(False, policy["mode"], f"outside {policy['sample_pct']}% sample")
    if policy["mode"] != "shadow" and breaker(db, svc.name)["open"]:
        return Decision(True, "shadow", "circuit breaker open, held in shadow")
    return Decision(True, policy["mode"], "policy")
