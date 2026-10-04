"""SQLite storage. One short-lived connection per operation keeps it thread safe."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created_at REAL, finished_at REAL,
  service TEXT, fingerprint TEXT, title TEXT,
  status TEXT, outcome TEXT, reason TEXT, mode TEXT,
  runner TEXT, model TEXT, prompt_version TEXT,
  incident TEXT, occurrences INTEGER DEFAULT 1,
  attempts INTEGER DEFAULT 0, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
  duration_ms INTEGER, diff TEXT, pr_body TEXT, branch TEXT, pr_url TEXT,
  guardrails TEXT, verify TEXT, agent TEXT, error TEXT,
  feedback TEXT, feedback_note TEXT, eval_run_id TEXT
);
CREATE INDEX IF NOT EXISTS runs_fp ON runs(fingerprint, created_at);
CREATE INDEX IF NOT EXISTS runs_created ON runs(created_at);
CREATE TABLE IF NOT EXISTS spans (
  id TEXT PRIMARY KEY, run_id TEXT, parent_id TEXT, name TEXT,
  start_ms REAL, end_ms REAL, status TEXT, attrs TEXT
);
CREATE INDEX IF NOT EXISTS spans_run ON spans(run_id);
CREATE TABLE IF NOT EXISTS policies (service TEXT PRIMARY KEY, mode TEXT, sample_pct INTEGER);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS eval_runs (
  id TEXT PRIMARY KEY, created_at REAL, runner TEXT, prompt_version TEXT, summary TEXT, cases TEXT
);
"""
JSON_COLS = {"incident", "guardrails", "verify", "agent", "attrs", "summary", "cases"}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    @staticmethod
    def _row(row) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for k in JSON_COLS & d.keys():
            if d[k] is not None:
                d[k] = json.loads(d[k])
        return d

    def query(self, sql: str, args=()) -> list[dict]:
        with self.conn() as c:
            return [self._row(r) for r in c.execute(sql, args).fetchall()]

    def one(self, sql: str, args=()) -> dict | None:
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def insert(self, table: str, **fields):
        fields = {k: json.dumps(v) if k in JSON_COLS and v is not None else v for k, v in fields.items()}
        cols = ",".join(fields)
        marks = ",".join("?" * len(fields))
        with self.conn() as c:
            c.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", list(fields.values()))

    def update_run(self, run_id: str, **fields):
        fields = {k: json.dumps(v) if k in JSON_COLS and v is not None else v for k, v in fields.items()}
        sets = ",".join(f"{k}=?" for k in fields)
        with self.conn() as c:
            c.execute(f"UPDATE runs SET {sets} WHERE id=?", [*fields.values(), run_id])

    def get_run(self, run_id: str) -> dict | None:
        return self.one("SELECT * FROM runs WHERE id=?", (run_id,))

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.insert("settings", key=key, value=value)


def now() -> float:
    return time.time()
