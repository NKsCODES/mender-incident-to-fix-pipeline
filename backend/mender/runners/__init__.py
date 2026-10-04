from mender.config import Settings
from mender.runners.base import AgentResult, Runner
from mender.runners.cursor_cli import CursorCliRunner
from mender.runners.replay import ReplayRunner


def make_runner(settings: Settings, name: str | None = None) -> Runner:
    name = name or settings.runner
    if name == "cursor":
        return CursorCliRunner(settings.cursor_bin, settings.cursor_model)
    if name == "replay":
        return ReplayRunner(settings.replay_dir)
    raise ValueError(f"unknown runner '{name}'")


__all__ = ["AgentResult", "Runner", "make_runner"]
