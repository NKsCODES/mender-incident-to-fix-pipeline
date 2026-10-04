"""Evidence that a patch is real: the new test must fail before the fix and the suite must pass after it."""
from __future__ import annotations

from mender.sandbox import Change, Sandbox, matches


def verify(sb: Sandbox, changes: list[Change], timeout: int) -> dict:
    new_tests = [c.path for c in changes if c.status == "A" and matches(c.path, sb.svc.test_globs) and c.path.endswith(".py")]
    result = {"new_tests": new_tests, "repro": "missing", "repro_output": "", "suite_passed": False, "suite_output": ""}

    if new_tests:
        copied = []
        try:
            for rel in new_tests:
                dst = sb.base / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text((sb.dir / rel).read_text())
                copied.append(dst)
            pre = sb.run_tests(timeout, new_tests, cwd=sb.base)
        finally:
            for dst in copied:
                dst.unlink(missing_ok=True)
        # pytest: 1 = tests ran and failed (a true reproduction), 0 = passed without the fix,
        # anything else (collection error, timeout) proves nothing either way.
        result["repro"] = {0: "not_reproduced", 1: "reproduced"}.get(pre.code, "inconclusive")
        result["repro_output"] = pre.output[-1500:]

    post = sb.run_tests(timeout)
    result["suite_passed"] = post.code == 0
    result["suite_timed_out"] = post.timed_out
    result["suite_output"] = post.output[-3000:]
    return result
