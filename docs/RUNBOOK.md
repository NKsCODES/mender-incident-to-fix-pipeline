# Runbook

First action for anything that looks wrong: **Rollout page → Stop everything.**
The kill switch only stops new work. In-flight runs finish in their sandbox and
cannot affect the customer repository unless they reach the publish step.

## Error rate high

Alert: `MenderErrorRateHigh`. More than 20% of runs end in `error`.

1. Runs page: open a run marked `Error`. The reason is one of:
   - `agent_error`: read the error on the agent attempt. Usually an expired `CURSOR_API_KEY`, a CLI upgrade that changed output, or a provider outage.
   - `agent_timeout`: see Agent timeouts below.
   - `pipeline_exception`: a bug in Mender. The error text and the failed span say where. Sandbox failures are usually a clone or a full disk.
   - `interrupted_by_restart`: a deploy happened mid-run. Re-send the incident.
2. If it is the CLI output format: fix `parse_stream`, run `pytest tests/test_cursor_runner.py`, redeploy.

## Breaker open

Alert: `MenderBreakerOpen`. A service is held in shadow.

1. Rollout page shows how many of the last 10 runs were bad.
2. If reviewers rejected the PRs: read the rejection notes on those runs. Add each as an eval case before changing the prompt.
3. The breaker closes by itself once good runs push the bad ones out of the window. Do not bypass it.

## Queue backlog

Alert: `MenderQueueBacklog`.

1. Check for an error storm: one deploy producing many distinct fingerprints. If so, set the service to `off` until the deploy is rolled back. Fixing errors from a bad deploy is the wrong response.
2. Otherwise raise `MENDER_WORKERS`. Each worker runs one agent and one test suite at a time.

## Spend spike

Alert: `MenderSpendSpike`.

1. Overview → cost per fix and tokens. Look for the highest-cost runs on the Runs page.
2. Usual causes: retries on a flaky suite (verify fails for reasons unrelated to the patch), or an incident storm. Lower the sample percent first, then fix the cause.

## Agent timeouts

Alert: `MenderAgentTimeouts`.

1. Open a timed-out run and read the tool calls. A long chain of reads means the code context was not enough and the agent is exploring. A stuck shell command means the agent ran something interactive.
2. Either raise `MENDER_AGENT_TIMEOUT_S` or tighten the prompt. Measure with the eval suite before and after.

## A bad PR was merged

1. Revert it in the customer repository. That comes first.
2. Mark the run `Rejected` with the reason.
3. Set the service to `shadow`.
4. Write the eval case that would have caught it, confirm the gate now fails, then fix the guardrail or prompt until it passes.
5. Write up what happened for the customer's engineering lead the same day.

## Debugging one run

The run page is ordered the way you debug: trace (which stage, how long), verification
(did the test reproduce, did the suite pass), guardrails, each agent attempt with its
summary, tool calls and tokens, then the patch. To replay locally:

```bash
python -m mender ingest fixtures/incidents/<event>.json --runner cursor --mode shadow
```
