"""Prometheus metrics. Alert rules that use these live in ops/alerts.yml."""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()
RUNS = Counter("mender_runs_total", "Finished pipeline runs", ["service", "outcome", "mode"], registry=REGISTRY)
STAGE_SECONDS = Histogram(
    "mender_stage_seconds", "Wall time per pipeline stage", ["stage"],
    buckets=(0.05, 0.25, 1, 5, 15, 60, 180, 600), registry=REGISTRY,
)
TOKENS = Counter("mender_agent_tokens_total", "Agent tokens", ["kind"], registry=REGISTRY)
COST = Counter("mender_agent_cost_usd_total", "Estimated agent spend", registry=REGISTRY)
VIOLATIONS = Counter("mender_guardrail_violations_total", "Guardrail hits", ["rule", "severity"], registry=REGISTRY)
ATTEMPTS = Counter("mender_agent_attempts_total", "Agent invocations", ["result"], registry=REGISTRY)
DUPLICATES = Counter("mender_duplicate_incidents_total", "Incidents folded into an existing run", ["service"], registry=REGISTRY)
BREAKER_OPEN = Gauge("mender_breaker_open", "1 when the circuit breaker holds a service in shadow", ["service"], registry=REGISTRY)
QUEUE_DEPTH = Gauge("mender_queue_depth", "Runs queued or running", registry=REGISTRY)
