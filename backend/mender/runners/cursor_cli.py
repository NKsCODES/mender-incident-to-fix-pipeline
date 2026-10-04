"""Drives the Cursor agent headless: `agent -p --force --output-format stream-json <prompt>`.

Flags and event shapes follow https://cursor.com/docs/cli/headless. The parser is
deliberately tolerant: unknown event types are ignored and token usage is read only
if the result event carries it, so a CLI update degrades telemetry rather than runs.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from mender.runners.base import AgentResult


def parse_stream(lines) -> AgentResult:
    res = AgentResult(ok=False)
    started: dict[str, dict] = {}
    for raw in lines:
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        kind, sub = ev.get("type"), ev.get("subtype")
        if kind == "system" and sub == "init":
            res.model = ev.get("model")
            res.session_id = ev.get("session_id")
        elif kind == "tool_call":
            call = ev.get("tool_call") or {}
            name = next(iter(call), "unknown")
            body = call.get(name) or {}
            args = body.get("args") or {}
            key = ev.get("call_id") or f"{name}:{len(started)}"
            if sub == "started":
                started[key] = {"tool": name.removesuffix("ToolCall"), "path": args.get("path"), "command": args.get("command"), "ok": None}
                res.tool_calls.append(started[key])
            elif sub == "completed" and key in started:
                started[key]["ok"] = "success" in (body.get("result") or {})
        elif kind == "result":
            res.ok = not ev.get("is_error", False) and sub in (None, "success")
            res.text = ev.get("result") or ""
            res.duration_ms = ev.get("duration_ms")
            res.session_id = ev.get("session_id") or res.session_id
            usage = ev.get("usage") or {}
            res.tokens_in = usage.get("inputTokens", usage.get("input_tokens"))
            res.tokens_out = usage.get("outputTokens", usage.get("output_tokens"))
            if not res.ok:
                res.error = (res.text or "agent reported an error")[:500]
    return res


class CursorCliRunner:
    name = "cursor"

    def __init__(self, binary: str = "agent", model: str | None = None):
        self.binary, self.model = binary, model

    def run(self, prompt: str, cwd: Path, timeout_s: int, context: dict) -> AgentResult:
        if not os.environ.get("CURSOR_API_KEY"):
            return AgentResult(ok=False, error="CURSOR_API_KEY is not set")
        cmd = [self.binary, "-p", "--force", "--output-format", "stream-json"]
        if self.model:
            cmd += ["--model", self.model]
        cmd.append(prompt)
        start = time.time()
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return AgentResult(ok=False, timed_out=True, error=f"agent exceeded {timeout_s}s", duration_ms=int((time.time() - start) * 1000))
        except FileNotFoundError:
            return AgentResult(ok=False, error=f"Cursor CLI '{self.binary}' not found. Install: curl https://cursor.com/install -fsS | bash")
        res = parse_stream(p.stdout.splitlines())
        res.duration_ms = res.duration_ms or int((time.time() - start) * 1000)
        if p.returncode != 0 and res.ok is False and not res.error:
            res.error = f"exit {p.returncode}: {p.stderr.strip()[-400:]}"
        return res
