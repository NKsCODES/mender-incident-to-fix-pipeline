"""Isolated checkout of the customer repo. The agent and the tests only ever touch this copy."""
from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mender.config import ServiceConfig

GIT_ID = ["-c", "user.name=mender", "-c", "user.email=mender@localhost", "-c", "commit.gpgsign=false"]
IGNORED = "__pycache__/\n*.pyc\n.pytest_cache/\nnode_modules/\n"
# Secrets must not reach customer test code or leak into captured output.
SCRUBBED_ENV = ("CURSOR_API_KEY", "MENDER_WEBHOOK_SECRET", "GH_TOKEN", "GITHUB_TOKEN")


@dataclass
class Change:
    path: str
    status: str  # A, M, D, R
    added: int
    deleted: int


@dataclass
class CmdResult:
    code: int
    output: str
    timed_out: bool = False


def matches(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


class Sandbox:
    def __init__(self, svc: ServiceConfig):
        self.svc = svc
        self.root = Path(tempfile.mkdtemp(prefix="mender-"))
        self.dir = self.root / "work"
        self.base = self.root / "base"  # pristine worktree, used to prove a new test fails before the fix
        if "://" in svc.repo or svc.repo.startswith("git@"):
            self._git(["clone", "--depth", "1", svc.repo, str(self.dir)], cwd=self.root)
        else:
            shutil.copytree(svc.repo, self.dir, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "node_modules"))
            self._git(["init", "-q", "-b", "main"])
            self._git(["add", "-A"])
            self._git([*GIT_ID, "commit", "-q", "-m", "baseline"])
        (self.dir / ".git" / "info").mkdir(exist_ok=True)
        (self.dir / ".git" / "info" / "exclude").write_text(IGNORED)
        self._git(["worktree", "add", "-q", "--detach", str(self.base), "HEAD"])

    def _git(self, args: list[str], cwd: Path | None = None, check: bool = True) -> str:
        p = subprocess.run(["git", *args], cwd=cwd or self.dir, capture_output=True, text=True)
        if check and p.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:3])} failed: {p.stderr.strip()[:400]}")
        return p.stdout

    def run(self, cmd: list[str], timeout: int, cwd: Path | None = None) -> CmdResult:
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTEST_ADDOPTS="-p no:cacheprovider")
        try:
            p = subprocess.run(cmd, cwd=cwd or self.dir, capture_output=True, text=True, timeout=timeout, env=env)
            return CmdResult(p.returncode, (p.stdout + p.stderr)[-6000:])
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return CmdResult(124, out[-6000:], timed_out=True)
        except FileNotFoundError as exc:
            return CmdResult(127, str(exc))

    def run_tests(self, timeout: int, paths: list[str] | None = None, cwd: Path | None = None) -> CmdResult:
        return self.run([*self.svc.test_cmd, *(paths or [])], timeout, cwd)

    def changes(self) -> list[Change]:
        self._git(["add", "-A"])
        status = {}
        for line in self._git(["diff", "--cached", "--name-status", "HEAD"]).splitlines():
            parts = line.split("\t")
            status[parts[-1]] = parts[0][0]
        out = []
        for line in self._git(["diff", "--cached", "--numstat", "HEAD"]).splitlines():
            added, deleted, path = line.split("\t", 2)
            out.append(Change(path, status.get(path, "M"), int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0))
        return out

    def diff(self) -> str:
        self._git(["add", "-A"])
        return self._git(["diff", "--cached", "HEAD"])

    def reset(self):
        self._git(["reset", "-q", "--hard", "HEAD"])
        self._git(["clean", "-q", "-fd"])

    def apply_patch(self, patch: str):
        p = subprocess.run(["git", "apply", "--whitespace=nowarn", "-"], cwd=self.dir, input=patch, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"patch does not apply: {p.stderr.strip()[:300]}")

    def commit_branch(self, branch: str, message: str):
        self._git(["checkout", "-q", "-b", branch])
        self._git(["add", "-A"])
        self._git([*GIT_ID, "commit", "-q", "-m", message])

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)
