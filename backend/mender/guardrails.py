"""Static checks on the agent's diff. Each rule exists because of a failure mode in docs/FAILURE_MODES.md."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from mender import metrics
from mender.config import DEPENDENCY_FILES, ServiceConfig
from mender.sandbox import Change, matches

BROAD_EXCEPT = re.compile(r"^\s*except\s*(?:\(?\s*(?:Base)?Exception\s*\)?\s*(?:as\s+\w+)?)?\s*:")
SKIP_MARKER = re.compile(r"pytest\.mark\.(skip|xfail)|pytest\.skip\(|unittest\.skip|\bit\.skip\(|\bxit\(|\.only\(")
SECRET = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|"
    r"(?i:(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-/+]{16,}['\"])"
)


@dataclass
class Violation:
    rule: str
    severity: str  # block | warn
    detail: str


def added_lines(diff: str) -> list[tuple[str, str]]:
    out, path = [], ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((path, line[1:]))
    return out


def check(diff: str, changes: list[Change], svc: ServiceConfig, verification: dict) -> list[dict]:
    v: list[Violation] = []
    total = sum(c.added + c.deleted for c in changes)
    if len(changes) > svc.max_files:
        v.append(Violation("max_files", "block", f"{len(changes)} files changed, limit {svc.max_files}"))
    if total > svc.max_lines:
        v.append(Violation("max_lines", "block", f"{total} lines changed, limit {svc.max_lines}"))
    for c in changes:
        if matches(c.path, svc.forbidden_paths):
            v.append(Violation("forbidden_path", "block", c.path))
        if matches(c.path.rsplit("/", 1)[-1], DEPENDENCY_FILES):
            v.append(Violation("dependency_change", "block", c.path))
        if c.status != "A" and matches(c.path, svc.test_globs):
            v.append(Violation("test_tampering", "block", f"existing test {'deleted' if c.status == 'D' else 'modified'}: {c.path}"))
    for path, line in added_lines(diff):
        if BROAD_EXCEPT.match(line):
            v.append(Violation("broad_except", "block", f"{path}: {line.strip()}"))
        if SKIP_MARKER.search(line):
            v.append(Violation("skip_marker", "block", f"{path}: {line.strip()}"))
        if SECRET.search(line):
            v.append(Violation("secret", "block", f"{path}: possible credential added"))
    repro = verification.get("repro")
    if repro == "missing":
        v.append(Violation("missing_regression_test", "warn", "no new test file accompanies the fix"))
    elif repro == "not_reproduced":
        v.append(Violation("test_does_not_reproduce", "block", "the new test passes without the fix, so it proves nothing"))
    elif repro == "inconclusive":
        v.append(Violation("repro_inconclusive", "warn", "the new test could not run against the old code"))
    for item in v:
        metrics.VIOLATIONS.labels(rule=item.rule, severity=item.severity).inc()
    return [asdict(item) for item in v]


def blocking(violations: list[dict]) -> list[dict]:
    return [x for x in violations if x["severity"] == "block"]
