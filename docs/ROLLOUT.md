# Rollout plan

Each phase has an exit criterion. A phase that misses it does not advance.
Rollback at any phase is one click: set the service mode back, or flip the kill switch.

| Phase | When | Mode | What happens | Exit criterion |
| --- | --- | --- | --- | --- |
| 0. First version | Days 1 to 3 | replay, then `cursor` on evals | Pipeline runs on captured incidents only | Eval gate passes on 10 or more of the customer's own past incidents |
| 1. Shadow | Week 1 | `shadow`, 100% | Live incidents run end to end, nothing leaves the system. Engineers grade a sample of patches in the dashboard | 20 graded runs, would-accept rate 60% or higher, no guardrail miss |
| 2. Suggest, sampled | Week 2 | `suggest`, 25% | Draft PRs for a quarter of incidents, one team | Accept rate 70% or higher over 15 PRs, no revert |
| 3. Suggest, full | Weeks 3 to 4 | `suggest`, 100% | Draft PRs for all eligible incidents | Accept rate holds for two weeks, reviewer time per PR is acceptable to the team |
| 4. Ready PRs | Week 5 on | `auto_pr` | PRs open ready for review. A human still merges | Reviewed per service. Never auto-merge |
| 5. Next service | After | back to `shadow` | Every new service starts at phase 1 | Same criteria |

## Controls

- **Kill switch.** Global. Every incoming incident is skipped. Use it first, ask questions after.
- **Service mode.** `off`, `shadow`, `suggest`, `auto_pr`. New services default to `shadow`.
- **Sampling.** Deterministic by incident fingerprint, so the same bug is always in or always out.
- **Circuit breaker.** If half of the last 10 runs for a service errored or were rejected by reviewers (minimum 5), the service is held in shadow until the window clears. Guardrail blocks do not count: a block is the system working.
- **Dedupe.** Repeat occurrences of the same fingerprint within 24 hours fold into the existing run.

## Changing the prompt or model

1. Bump `PROMPT_VERSION`.
2. Run `make eval-cursor`. The gate fails the change if resolve rate drops below 55%, false-fix rate rises above 15%, or more than one good patch is blocked.
3. Compare with the previous version on the Evals page.
4. Roll out behind `shadow` for a day before promoting.

Every rejected PR becomes a new eval case: the incident JSON, plus a held-out
test encoding what the reviewer said was wrong.
