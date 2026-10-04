import json
import stat

from mender.runners.cursor_cli import CursorCliRunner, parse_stream

EVENTS = [
    {"type": "system", "subtype": "init", "model": "test-model", "session_id": "s1"},
    {"type": "tool_call", "subtype": "started", "call_id": "c1", "tool_call": {"readToolCall": {"args": {"path": "a.py"}}}},
    {"type": "tool_call", "subtype": "completed", "call_id": "c1", "tool_call": {"readToolCall": {"args": {"path": "a.py"}, "result": {"success": {"totalLines": 3}}}}},
    {"type": "tool_call", "subtype": "started", "call_id": "c2", "tool_call": {"writeToolCall": {"args": {"path": "b.py"}}}},
    {"type": "tool_call", "subtype": "completed", "call_id": "c2", "tool_call": {"writeToolCall": {"args": {"path": "b.py"}, "result": {"error": {"message": "denied"}}}}},
    {"type": "some_future_event", "x": 1},
    {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 1234, "result": "done", "session_id": "s1"},
]


def test_parse_stream_tolerates_noise_and_unknown_events():
    res = parse_stream(["not json", "{broken", *[json.dumps(e) for e in EVENTS]])
    assert res.ok and res.model == "test-model" and res.duration_ms == 1234 and res.text == "done"
    assert [(c["tool"], c["path"], c["ok"]) for c in res.tool_calls] == [("read", "a.py", True), ("write", "b.py", False)]
    assert res.tokens_in is None  # absent usage stays unknown instead of being guessed


def test_parse_stream_without_result_is_failure():
    assert not parse_stream([json.dumps(EVENTS[0])]).ok


def test_runner_invokes_cli_with_documented_flags(tmp_path, monkeypatch):
    fake = tmp_path / "agent"
    fake.write_text(
        "#!/bin/sh\n"
        'echo "$@" > args.txt\n'
        "echo patched > fixed.txt\n"
        "echo '{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"duration_ms\":5,\"result\":\"ok\",\"usage\":{\"inputTokens\":10,\"outputTokens\":2}}'\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CURSOR_API_KEY", "test")
    res = CursorCliRunner(str(fake), model="m1").run("fix it", tmp_path, 10, {})
    assert res.ok and (res.tokens_in, res.tokens_out) == (10, 2)
    assert (tmp_path / "args.txt").read_text().strip() == "-p --force --output-format stream-json --model m1 fix it"
    assert (tmp_path / "fixed.txt").exists()


def test_runner_reports_missing_key_binary_and_timeout(tmp_path, monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    assert "CURSOR_API_KEY" in CursorCliRunner().run("x", tmp_path, 5, {}).error
    monkeypatch.setenv("CURSOR_API_KEY", "test")
    assert "not found" in CursorCliRunner("definitely-not-a-binary").run("x", tmp_path, 5, {}).error
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\nsleep 5\n")
    slow.chmod(0o755)
    assert CursorCliRunner(str(slow)).run("x", tmp_path, 1, {}).timed_out
