# Discovery

How the engagement starts, before any code. The scenario below is illustrative
(the "checkout" team is the sample service in `fixtures/`), but the questions,
the metric definitions and the order are the ones to reuse.

## 1. Find the real bottleneck

The stated ask is usually "we want AI to fix our bugs". The discovery call is to
find out where engineer time actually goes. Questions that separate the two:

- Walk me through the last three production errors. Who noticed, who picked it up, how long until a fix merged?
- Of the errors in your tracker right now, how many are older than 30 days? Why are they still open?
- What share of on-call time is diagnosis, and what share is writing the fix?
- Which errors would you never let an agent touch? (This sets the forbidden paths.)
- What does a PR need before your team will merge it without asking questions?
- How good is test coverage on the services that page most?

Typical finding: the fix is rarely the slow part. The long tail of low-severity
errors never gets picked up at all, because each one costs 30 to 60 minutes of
context loading for a small change. That is the bottleneck Mender targets: the
errors nobody has time to start.

Signals that this workflow is the wrong one: no runnable test suite, incidents
that are mostly infrastructure or data problems, or a team whose bottleneck is
review capacity (more PRs would make things worse).

## 2. Success metrics

Agreed with the engineering lead before building, each with a source of truth.

| Metric | Definition | Source | Initial target |
| --- | --- | --- | --- |
| PR accept rate | accepted / reviewed Mender PRs | reviewer verdict on the run | 70% or higher |
| False-fix rate | shipped patches that fail the held-out test | eval suite | under 15% |
| Fix rate | runs ending in a PR or shadow pass / runs attempted | `/api/stats` | 40% or higher |
| Time to fix | incident received to PR opened, p50 | run duration | under 15 minutes |
| Cost per accepted fix | agent spend / accepted PRs | tokens × contract rate | under the cost of 30 engineer minutes |
| Backlog | open errors older than 30 days | customer error tracker | down by half in a quarter |

Accept rate is the headline. Fix rate alone rewards opening bad PRs.

Guardrail metrics that must not get worse: reverted Mender PRs (target zero),
reviewer time per PR, and on-call pages caused by a Mender change (target zero).

## 3. Scope for version one

In: Python services with a test suite, exceptions with an in-app stack frame,
one service, shadow mode.
Out: infrastructure incidents, data fixes, schema changes, anything under the
paths the team named as off limits, auto-merge.

## 4. What to bring back to the customer every week

The Overview page numbers, the three most instructive rejected PRs with the
reason, the eval trend, and the next rollout step with its exit criteria.
