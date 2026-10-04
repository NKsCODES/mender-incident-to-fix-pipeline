"""The fix prompt. Bump PROMPT_VERSION on any change so eval runs stay comparable."""
from __future__ import annotations

import json

PROMPT_VERSION = "fix-v3"

RULES = """Rules:
1. First add ONE new regression test file under tests/ that fails on the current code for the same reason as the incident. Do not edit or delete existing tests.
2. Then make the smallest change that fixes the root cause. Follow the behaviour documented in docstrings and existing tests.
3. Never hide the error: no bare or broad except, no skip or xfail markers, no default that masks bad input.
4. Do not touch CI, infrastructure, migrations or dependency files.
5. If the intended behaviour is not determinable from the code, make NO changes and explain what is unclear.
6. Finish with two short paragraphs: root cause, then what you changed."""


def build_prompt(incident: dict, context: list[dict], retry: dict | None = None) -> str:
    exc = incident["exception"]
    frames = "\n".join(
        f"  {f.get('filename')}:{f.get('lineno')} in {f.get('function')}: {f.get('context_line', '')}"
        for f in exc.get("frames", [])
    )
    parts = [
        f"A production incident occurred in service '{incident['service']}' ({incident.get('environment', 'unknown')}, release {incident.get('release', 'unknown')}).",
        f"Exception: {exc['type']}: {exc.get('value', '')}",
        f"Occurrences: {incident.get('count', 1)}",
        f"Stack (most recent call last):\n{frames}",
    ]
    if incident.get("request"):
        parts.append("Triggering request:\n" + json.dumps(incident["request"], indent=2)[:1500])
    for c in context:
        parts.append(f"{c['filename']} around line {c['lineno']}:\n{c['snippet']}")
    parts.append(RULES)
    if retry:
        parts.append(
            "Your previous attempt was rejected and has been reverted.\n"
            f"Reason: {retry['reason']}\nPrevious diff:\n{retry['diff'][:4000]}\nTest output:\n{retry['output'][-3000:]}"
        )
    return "\n\n".join(parts)
