# Reusable patterns and product feedback

What carries over to the next customer, and what should go back to the Cursor product team.

## Patterns

1. **Evidence, not assertion.** A patch is accepted only with a test that fails before it and passes after it. Running the new test against a pristine worktree is cheap and removes a whole class of fake fixes. Reusable for migrations and refactors: "the old behaviour test still passes".
2. **Guardrails on the diff, not the prompt.** The prompt asks; the diff check enforces. Every rule in `guardrails.py` exists because a prompt instruction alone was not enough.
3. **Held-out tests for evals.** The agent sees the incident; the eval scores against a contract test it never saw. This is what makes false-fix rate measurable.
4. **Replay runner.** A scripted stand-in for the agent turns the harness into ordinary testable software and keeps CI free. Bad replays are regression tests for guardrails.
5. **Shadow first, with a breaker.** Every new service starts where it cannot hurt anyone, and human rejections automatically pull it back there.
6. **Rejections become eval cases.** The feedback endpoint is the intake for the eval suite.
7. **Versioned prompts.** `PROMPT_VERSION` is stored on every run and eval, so a regression can be traced to a change.
8. **The same rule for humans and automation.** `.cursor/rules/incident-fix.mdc` gives interactive Cursor sessions the same incident-fix discipline the pipeline enforces.

The same skeleton (gate → sandbox → agent → verify → guardrails → publish) fits the
other workflows in the role: swap the trigger and the verifier.

| Workflow | Trigger | Verifier |
| --- | --- | --- |
| Large refactor or migration | A list of files or call sites | Suite passes, type check passes, API surface unchanged |
| PR review loop | PR opened | Reviewer accept rate on comments, false-positive rate |
| Spec to implementation | Spec document | Acceptance tests written from the spec before the code |

## Feedback for the Cursor product

Friction met while building this, phrased as requests.

1. **Token usage in headless output.** The headless docs show `duration_ms` on the result event but do not document token usage. Cost per run is the first thing an engineering leader asks for. A documented `usage` object on the result event would remove guesswork. Mender reads it if present.
2. **A machine-readable "declined" result.** When the agent decides not to change anything, that is only visible in prose. A structured outcome (changed, declined with reason) would let pipelines tell a refusal from a failure.
3. **Path and command policy for `--force`.** Headless runs are all or nothing. An allowlist or denylist for writable paths and shell commands, enforced by the CLI, would move guardrails like `forbidden_path` and `test_tampering` from after-the-fact checks to prevention.
4. **Stable event schema with a version field.** A `schema_version` on stream events would let integrations fail loudly on a breaking change instead of silently losing telemetry.
5. **Trace correlation.** Accepting a caller-supplied trace or request id, and echoing it in every event, would let customer tracing systems join agent activity to their own spans.
