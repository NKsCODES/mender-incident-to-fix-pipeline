"""Minimal span tracing persisted next to the run, so every PR has a replayable trace."""
from __future__ import annotations

import time
from contextlib import contextmanager

from mender import metrics
from mender.db import Database, new_id


class Span:
    def __init__(self, name: str, attrs: dict):
        self.name, self.attrs, self.status = name, attrs, "ok"

    def set(self, **attrs):
        self.attrs.update(attrs)


class Tracer:
    def __init__(self, db: Database, run_id: str):
        self.db, self.run_id, self._stack = db, run_id, []

    @contextmanager
    def span(self, name: str, **attrs):
        span = Span(name, dict(attrs))
        span_id = new_id("sp")
        parent = self._stack[-1] if self._stack else None
        self._stack.append(span_id)
        start = time.time()
        try:
            yield span
        except Exception as exc:
            span.status = "error"
            span.attrs["error"] = f"{type(exc).__name__}: {exc}"[:500]
            raise
        finally:
            end = time.time()
            self._stack.pop()
            metrics.STAGE_SECONDS.labels(stage=name).observe(end - start)
            self.db.insert(
                "spans", id=span_id, run_id=self.run_id, parent_id=parent, name=name,
                start_ms=start * 1000, end_ms=end * 1000, status=span.status, attrs=span.attrs,
            )
