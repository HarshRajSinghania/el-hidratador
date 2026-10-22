# Failure Playbook

| Category | Trigger | Ledger effect | How to recover |
|----------|---------|---------------|----------------|
| `lease_expired` | A lease ran out | Session `expired`, task `BLOCKED`, scope reservation kept | `hidratador reconcile`, then `decide <id> retry --reason "..."` and `start` again |
| `budget` | Cumulative tokens reached the budget | Task `BLOCKED` | Raise the budget deliberately with `update_task`, or accept the smaller scope of work |
| `no_progress` | Three checkpoints with identical evidence | Session `FAILED`, task `BLOCKED` | Change the approach, or regenerate the context with the error attached |
| `tool` | A tool or adapter failed | Task `BLOCKED` | Fix the tool, then `decide <id> retry` |
| `dependency` | A prerequisite is missing | Task `BLOCKED` | Land the dependency, then retry |

## Lease expiry

```bash
hidratador status | jq '.sessions[] | select(.status == "expired")'
hidratador decide M-1001 retry --reason "Reconciled the expired lease"
hidratador start M-1001 --owner terminal-2
```

A blocked ticket keeps its resource reservation until an operator decides.
That is deliberate: two workers must not touch the same scope by accident.

## Budget exhaustion

```bash
hidratador decide M-1001 retry --reason "Budget exhausted; scope reduced"
```

Retry does not reset the counter. Tokens are cumulative on purpose — a retry
that spends the same budget again is a runaway loop, and the ledger should say
so.

## No progress

Three checkpoints with the same evidence hash mean the worker is looping.
Either give it different context, change the plan, or halt the DAG for an
operator.

## Failure fingerprints

Failures group by `sha256(category:summary)[:16]`. A category that keeps
recurring with the same summary is usually an environment problem, not a
worker problem.

```bash
hidratador status | jq '.failures[] | {category, summary, occurrences}'
```

## When to stop and ask

- The right action is unclear.
- The scope would need to grow.
- The acceptance criteria cannot be met as written.
- A refund, a deletion, or anything outside the task's scope is implied.
