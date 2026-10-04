# Failure modes and tradeoffs

## Model failure modes

Each row has an eval case that reproduces it and a control that handles it.

| Failure | What it looks like | Control | Eval case |
| --- | --- | --- | --- |
| Hides the error | Wraps the failing line in `except Exception` and returns a default | `broad_except` guardrail blocks; no retry | inventory-unknown-sku |
| Rewrites the tests | Edits an existing test so its own behaviour passes | `test_tampering` blocks any change to a pre-existing test file | cart-empty |
| Wrong first guess | Plausible fix that contradicts the documented contract | Its own regression test fails, test output goes back to the agent, one retry | tax-missing-region |
| Fixes only the reported input | Handles `'10%'` but not `' 15 % '` or `150%` | **Not caught by the harness.** Human review. Measured as false-fix rate | coupon-percent-sign |
| Ambiguous intent | Nothing in the code says what correct behaviour is | Prompt rule 5: change nothing and explain. Recorded as `no_fix` | shipping-drone |
| Test that proves nothing | New test passes even without the fix | Test is run against a pristine worktree and must fail there | unit test |
| Skips its way to green | Adds `skip` or `xfail` | `skip_marker` blocks | unit test |
| Scope creep | Touches CI, migrations, dependencies, or a large diff | `forbidden_path`, `dependency_change`, `max_files`, `max_lines` | unit test |
| Runs forever | Agent explores without converging | Hard timeout, recorded as `agent_timeout`, feeds the breaker | unit test |

### The one that gets through

The coupon case passes every automated check and is still wrong. More guardrails
do not fix this class: the patch is small, clean, tested and reproduces the
incident. What reduces it is prompt work (rule 2 points the agent at the
docstring contract) and measurement (the held-out test and the false-fix rate).
What contains it is that Mender never merges. This is the number to be most
honest about with a customer.

## System failure modes

| Failure | Handling |
| --- | --- |
| Webhook spoofing | HMAC signature on the request body when `MENDER_WEBHOOK_SECRET` is set |
| Path traversal through stack frame filenames | Frames are resolved and must sit inside the repository |
| Secrets reaching customer test code | `CURSOR_API_KEY`, GitHub tokens and the webhook secret are stripped from the test environment |
| Error storm from a bad deploy | Fingerprint dedupe, sampling, bounded worker pool, queue depth alert |
| Crash or deploy mid-run | Orphaned runs are closed as `interrupted_by_restart` on startup |
| Flaky customer test suite | Shows up as `verify_failed` with the suite output. Not solved here: quarantine the flaky tests |
| CLI output format changes | Parser ignores unknown events; missing usage becomes unknown cost, not a guess |
| Hostile repository content steering the agent | Sandbox only, no network credentials for the customer's systems, guardrails on the output, human review. Not eliminated |

## Latency and cost tradeoffs

| Lever | More of it | Less of it | Default |
| --- | --- | --- | --- |
| Retries (`MENDER_MAX_ATTEMPTS`) | Higher fix rate, up to 2× cost and time on hard cases | Cheaper, more `verify_failed` | 2 |
| Code context per frame | Fewer agent read calls, larger prompt | Agent explores more, slower, sometimes better | 12 lines either side, 4 frames |
| Model choice (`MENDER_CURSOR_MODEL`) | Stronger model: fewer false fixes, higher cost | Faster and cheaper, more retries | Cursor default |
| Agent timeout | Fewer timeouts on large repos | Faster failure, lower worst-case spend | 600 s |
| Full suite vs targeted tests | Full suite catches regressions elsewhere | Targeted is faster on big repos | Full suite |
| Sampling | More coverage | Bounded spend while trust is built | 100% in shadow |

Verification dominates wall time on small repositories and the agent dominates on
large ones, so read the stage latency table before tuning either. Cost is reported
as unknown unless token usage is present and a rate is configured. A made-up cost
number is worse than none.
