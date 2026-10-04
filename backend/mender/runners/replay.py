"""Deterministic stand-in for the agent, used offline, in CI and in demos.

It applies hand-written edits from fixtures/replays/<event_id>.yaml. Several replays
are intentionally bad (swallowed exceptions, edited tests, a plausible but wrong fix)
so the harness around the agent can be regression tested without spending tokens.
Numbers produced with this runner describe the harness, not model quality.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from mender.runners.base import AgentResult


class ReplayRunner:
    name = "replay"

    def __init__(self, replay_dir: str):
        self.dir = Path(replay_dir)

    def run(self, prompt: str, cwd: Path, timeout_s: int, context: dict) -> AgentResult:
        event_id = Path(str(context.get("event_id", ""))).name
        path = self.dir / f"{event_id}.yaml"
        if not path.is_file():
            return AgentResult(ok=False, error=f"no replay recorded for event '{event_id}'")
        attempts = yaml.safe_load(path.read_text())["attempts"]
        step = attempts[min(context.get("attempt", 1), len(attempts)) - 1]
        if step.get("timeout"):
            return AgentResult(ok=False, timed_out=True, error=f"agent exceeded {timeout_s}s", model="replay")
        calls = []
        for edit in step.get("edits", []):
            target = cwd / edit["path"]
            if "find" in edit:
                text = target.read_text()
                if text.count(edit["find"]) != 1:
                    return AgentResult(ok=False, error=f"replay edit did not match once in {edit['path']}", model="replay")
                target.write_text(text.replace(edit["find"], edit["replace"]))
                calls += [{"tool": "read", "path": edit["path"], "ok": True}, {"tool": "edit", "path": edit["path"], "ok": True}]
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(edit["content"])
                calls.append({"tool": "write", "path": edit["path"], "ok": True})
        return AgentResult(
            ok=True, text=step.get("text", ""), model="replay", duration_ms=step.get("duration_ms"),
            tokens_in=step.get("tokens_in"), tokens_out=step.get("tokens_out"), tool_calls=calls,
        )
