"""Normalise an incident, fingerprint it for dedupe, and pull code context for the prompt."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def top_frame(incident: dict) -> dict | None:
    frames = [f for f in incident["exception"].get("frames", []) if f.get("in_app", True)]
    return frames[-1] if frames else None


def fingerprint(incident: dict) -> str:
    """Stable across occurrences: line numbers and literal values are left out on purpose,
    so the same bug still dedupes after an unrelated edit shifts the file."""
    exc = incident["exception"]
    frame = top_frame(incident) or {}
    message = re.sub(r"\d+|'[^']*'|\"[^\"]*\"", "?", exc.get("value", ""))[:120]
    raw = "|".join([incident["service"], exc["type"], frame.get("filename", ""), frame.get("function", ""), message])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def title(incident: dict) -> str:
    exc = incident["exception"]
    frame = top_frame(incident)
    where = f" in {frame['function']} ({frame['filename']})" if frame else ""
    return f"{exc['type']}: {exc.get('value', '')[:80]}{where}"


def safe_path(repo: Path, rel: str) -> Path | None:
    """Frame filenames arrive from an unauthenticated-by-default webhook. Never read outside the repo."""
    try:
        target = (repo / rel).resolve()
    except (OSError, ValueError):
        return None
    root = repo.resolve()
    return target if target.is_file() and root in target.parents else None


def code_context(repo: Path, incident: dict, radius: int = 12, max_frames: int = 4) -> list[dict]:
    out = []
    frames = [f for f in incident["exception"].get("frames", []) if f.get("in_app", True)]
    for frame in reversed(frames[-max_frames:]):
        path = safe_path(repo, frame.get("filename", ""))
        if path is None:
            continue
        lines = path.read_text(errors="replace").splitlines()
        lineno = int(frame.get("lineno") or 1)
        lo, hi = max(1, lineno - radius), min(len(lines), lineno + radius)
        snippet = "\n".join(
            f"{'>>' if n == lineno else '  '} {n:4d} | {lines[n - 1]}" for n in range(lo, hi + 1)
        )
        out.append({"filename": frame["filename"], "lineno": lineno, "function": frame.get("function"), "snippet": snippet})
    return out
