"""Settings come from the environment; per-service policy comes from mender.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_FORBIDDEN = [
    ".github/**", ".gitlab-ci.yml", "migrations/**", "**/migrations/**",
    "infra/**", "terraform/**", "Dockerfile", "docker-compose*.yml", ".env*", ".cursor/**",
]
DEPENDENCY_FILES = [
    "requirements*.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile*", "poetry.lock",
    "uv.lock", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.mod", "go.sum",
]


@dataclass
class ServiceConfig:
    name: str
    repo: str  # local path or git URL
    test_cmd: list[str] = field(default_factory=lambda: ["python", "-m", "pytest", "-q", "-x"])
    test_globs: list[str] = field(default_factory=lambda: ["tests/**", "test_*.py", "**/test_*.py", "**/*_test.py"])
    forbidden_paths: list[str] = field(default_factory=lambda: list(DEFAULT_FORBIDDEN))
    max_files: int = 6
    max_lines: int = 150
    default_mode: str = "shadow"
    github_repo: str | None = None  # owner/name, only used when MENDER_PUBLISH=1


@dataclass
class Settings:
    db_path: str = str(ROOT / "data" / "mender.db")
    services_file: str = str(ROOT / "mender.yaml")
    replay_dir: str = str(ROOT / "fixtures" / "replays")
    dashboard_dir: str = str(ROOT / "dashboard" / "dist")
    runner: str = "replay"  # replay | cursor
    cursor_bin: str = "agent"
    cursor_model: str | None = None
    agent_timeout_s: int = 600
    test_timeout_s: int = 300
    max_attempts: int = 2
    workers: int = 2
    dedupe_hours: int = 24
    webhook_secret: str | None = None
    publish: bool = False
    # USD per million tokens. Zero means unknown, and cost is then reported as null.
    price_in: float = 0.0
    price_out: float = 0.0


def load_settings(**overrides) -> Settings:
    env = os.environ
    s = Settings()
    for name, cast in [
        ("db_path", str), ("services_file", str), ("replay_dir", str), ("dashboard_dir", str),
        ("runner", str), ("cursor_bin", str), ("cursor_model", str), ("webhook_secret", str),
        ("agent_timeout_s", int), ("test_timeout_s", int), ("max_attempts", int), ("workers", int),
        ("dedupe_hours", int), ("price_in", float), ("price_out", float),
    ]:
        raw = env.get(f"MENDER_{name.upper()}")
        if raw not in (None, ""):
            setattr(s, name, cast(raw))
    s.publish = env.get("MENDER_PUBLISH") == "1"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def load_services(path: str) -> dict[str, ServiceConfig]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    base = Path(path).resolve().parent
    out = {}
    for name, raw in (data.get("services") or {}).items():
        raw = dict(raw)
        repo = raw.pop("repo")
        if "://" not in repo and not repo.startswith("git@"):
            repo = str((base / repo).resolve())
        extra = raw.pop("extra_forbidden_paths", [])
        svc = ServiceConfig(name=name, repo=repo, **raw)
        svc.forbidden_paths = svc.forbidden_paths + extra
        out[name] = svc
    return out
