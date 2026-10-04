from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class AgentResult:
    ok: bool
    text: str = ""
    model: str | None = None
    duration_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None
    timed_out: bool = False
    session_id: str | None = None


class Runner(Protocol):
    name: str

    def run(self, prompt: str, cwd: Path, timeout_s: int, context: dict) -> AgentResult: ...
