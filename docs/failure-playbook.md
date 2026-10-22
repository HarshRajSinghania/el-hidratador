# Failure playbook

Every refusal in this package is a recorded fact, not a silent degradation. This page lists every
failure category, what puts a task into it, what it does to the ledger, and the exact commands that
recover from it.

Failures carry two things: a **category** from a fixed taxonomy, and a **fingerprint** —
`sha256(category:summary)` truncated to 16 hex characters. The fingerprint is the grouping key, so
recurring failures of the same kind collapse into one row with an occurrence count.

```text
failures(task_id, session_id, category, fingerprint, summary, created)
```

---

## The categories

| Category | Trigger | Ledger effect | Operator options |
|----------|---------|---------------|------------------|
| `lease_expired` | `reconcile()` finds an active session whose `lease_until` has passed | Session → `expired`, task → `BLOCKED`, a failure row is written | Retry with a new lease; cancel the task; investigate whether the worker is still alive |
| `budget` | A checkpoint reaches the cumulative token budget, or `start()` finds cumulative tokens already at the budget | Session → `failed`, task → `BLOCKED`, a failure row is written | Raise the budget, then retry; cancel; or split the work into smaller tickets |
| `no_progress` | Three consecutive checkpoints cite identical evidence | Session → `failed`, task → `BLOCKED`, a failure row is written | Regenerate the context with the error attached and retry; halt for intervention; cancel |
| `tool` | Explicitly reported by the worker via `fail --category tool` | Session → `failed`, task → `BLOCKED`, a failure row is written | Fix the tooling and retry; escalate; cancel |
| `dependency` | Explicitly reported by the worker via `fail --category dependency` | Session → `failed`, task → `BLOCKED`, a failure row is written | Satisfy the dependency and retry; halt for intervention; cancel |

Three of the five categories are produced automatically by the ledger. `tool` and `dependency` are
only ever produced by an explicit `fail` call — the ledger cannot infer that a tool broke.

Note that `fail` accepts any of the five categories, including `lease_expired`, `budget`, and
`no_progress`. The automatic paths use those categories because that is what actually happened.

---

## The three recovery paths

Every blocked task recovers along one of three paths. They are not exclusive; most incidents use one
path and then, if it does not work, escalate to the next.

### Path A — regenerate the context with error context

The worker hit a problem that the packet did not contain. Attach the error as high-priority context
and re-expand, so the next attempt starts with the failure in view.

```bash
# 1. Attach the error text as high-priority context
hidratador context-add M-1001 \
  --text "Previous attempt failed: TypeError: cannot read property 'id' of undefined in router.py" \
  --source-label "failure/attempt-1" --priority 100

# 2. Re-expand and confirm the error is inside the untrusted block
hidratador expand M-1001 --max-bytes 12000 | jq -r '.prompt'

# 3. Retry and restart
hidratador decide M-1001 retry --reason "Regenerated packet with the attempt-1 error attached"
hidratador start M-1001 --owner terminal-1 --lease 900
```

The error text lands inside the `--- BEGIN UNTRUSTED CONTEXT ---` banner. Context is untrusted
reference data, never authorization: the error is reference data about a past failure, not an
instruction, and it cannot authorise anything.

### Path B — halt for operator intervention

The problem is not the worker's fault. A missing dependency, a wrong scope reservation, or an
ambiguous requirement needs a human.

```bash
# Leave the task BLOCKED and inspect why
hidratador task-show M-1001
hidratador --compact status | jq '.failures'

# Check whether another task is holding the same scope keys
hidratador --compact task-list --status IN_PROGRESS | jq '.tasks[] | {id, scope}'
hidratador --compact task-list --status BLOCKED   | jq '.tasks[] | {id, scope}'
```

A `BLOCKED` task still holds its scope reservation. Scope keys are only released when the task
moves to `READY` (via `decide retry`) or to `CANCELLED`.

```bash
# Either release the scope and let the other task proceed
hidratador decide M-1001 cancel --reason "Superseded; requirement is ambiguous"

# Or keep it blocked and intervene out of band
```

### Path C — retry with a new lease

The work is fine; the lease or the attempt was not. `decide retry` returns the task to `READY` and a
fresh `start` acquires a new lease.

```bash
hidratador decide M-1001 retry --reason "Worker restarted; continuing from the last checkpoint"
hidratador start M-1001 --owner terminal-2 --lease 1800
```

Cumulative tokens are preserved across the retry. The new session continues against the same
budget.

---

## Worked example: lease expiry

A worker takes a lease, then dies without checking in.

```bash
$ hidratador start M-2001 --owner terminal-1 --lease 1
{
  "command": "start",
  "lease_until": 1792655373.3363001,
  "lease_until_iso": "2026-10-22T07:49:33.336Z",
  "ok": true,
  "session_id": "accbac8058fb4f309f27663ef28ba517",
  "task_id": "M-2001",
  "token_budget": 100,
  "tokens_used": 0
}
```

The lease expires. Any ledger command that reconciles will notice:

```bash
$ hidratador reconcile
{
  "command": "reconcile",
  "expired_count": 1,
  "expired_tasks": ["M-2001"],
  "ok": true
}
```

The task is now blocked and the failure is on record:

```bash
$ hidratador --compact task-show M-2001 | jq '{id, status}'
{
  "id": "M-2001",
  "status": "BLOCKED"
}

$ hidratador --compact status | jq '.failures'
[
  {
    "category": "lease_expired",
    "fingerprint": "9dd627750523e987",
    "last_seen": 1792655374.451413,
    "last_seen_iso": "2026-10-22T07:49:34.451Z",
    "occurrences": 1,
    "summary": "Ownership expired; reconcile the old worker before retrying."
  }
]
```

**Recovery.** Confirm the old worker is really gone, then take a new lease:

```bash
$ hidratador decide M-2001 retry --reason "Original worker terminal-1 confirmed stopped"
{
  "command": "decide",
  "decision": "retry",
  "ok": true,
  "status": "READY",
  "task_id": "M-2001"
}

$ hidratador start M-2001 --owner terminal-2 --lease 900
```

If the old worker is still running, do **not** retry. Two workers on the same scope is the exact
situation the lease exists to prevent.

---

## Worked example: budget exhaustion

A task with a 100-token budget overshoots it.

```bash
$ hidratador checkpoint c6be5dbd657d4b4f82572b50d852674f \
    --summary "s1" --evidence "e1" --next "n1" --tokens 150
{
  "command": "checkpoint",
  "evidence_hash": "8b5cc4df7eec7d32a7814eca4af047ae33b2d52342667715682e19c25b0b9faa",
  "ok": true,
  "session_id": "c6be5dbd657d4b4f82572b50d852674f",
  "stagnant": 0,
  "status": "blocked",
  "tokens": 150
}
```

The task is blocked and a `budget` failure is recorded. A retry does not reset the counter:

```bash
$ hidratador decide M-3001 retry --reason "budget increased"
{
  "command": "decide",
  "decision": "retry",
  "ok": true,
  "status": "READY",
  "task_id": "M-3001"
}

$ hidratador start M-3001 --owner terminal-1 --lease 900
{
  "error": "task token budget exhausted across attempts",
  "kind": "BudgetExceeded",
  "ok": false
}
```

Exit code `2`. The task is ready but cannot start, because cumulative tokens across *every* attempt
have reached the budget.

**Recovery.** Raise the budget. The CLI has no `task-update` command, so this is a library
operation:

```python
from el_hidratador import Ledger

with Ledger("/tmp/ledger.sqlite") as ledger:
    ledger.add_task(
        "M-3001",
        objective="Add GET /healthz",
        acceptance="200 with the request id header",
    )
    ledger.update_task("M-3001", token_budget=8000)
```

```bash
$ hidratador start M-3001 --owner terminal-1 --lease 900
```

The alternative recovery is to split the work: create smaller tickets with their own budgets and
let them succeed independently.

---

## Worked example: no progress

The worker reports the same evidence three times in a row. The evidence hash is identical, so the
ledger concludes it is looping.

```bash
$ hidratador --compact checkpoint 2dcf538a2e104063877178a45ce13e31 \
    --summary "s1" --evidence "same-evidence" --next "n1" --tokens 100
{"command": "checkpoint", "evidence_hash": "9c01f1ceb...", "ok": true, "status": "active", "stagnant": 0, "tokens": 100}

$ hidratador --compact checkpoint 2dcf538a2e104063877178a45ce13e31 \
    --summary "s2" --evidence "same-evidence" --next "n2" --tokens 200
{"command": "checkpoint", "evidence_hash": "9c01f1ceb...", "ok": true, "status": "active", "stagnant": 1, "tokens": 200}

$ hidratador --compact checkpoint 2dcf538a2e104063877178a45ce13e31 \
    --summary "s3" --evidence "same-evidence" --next "n3" --tokens 300
{"command": "checkpoint", "evidence_hash": "9c01f1ceb...", "ok": true, "status": "blocked", "stagnant": 2, "tokens": 300}
```

The `stagnant` counter is the number of consecutive repeats. At `2` the third identical hash has
been seen, so the task blocks and a `no_progress` failure is recorded:

```bash
$ hidratador --compact status | jq '.failures'
[
  {
    "category": "no_progress",
    "fingerprint": "f2c3f7960fd90fd2",
    "last_seen": 1792655384.242118,
    "last_seen_iso": "2026-10-22T07:49:44.242Z",
    "occurrences": 1,
    "summary": "Three consecutive checkpoints cite identical evidence."
  }
]
```

**Recovery.** Usually Path A — the worker was missing information. Attach what it should have had
and retry:

```bash
hidratador context-add M-4001 \
  --text "Router registration requires the router instance from the app factory, not the module-level default." \
  --source-label "failure/hint-1" --priority 100

hidratador decide M-4001 retry --reason "Attached the app-factory hint; previous attempt looped"
hidratador start M-4001 --owner terminal-1 --lease 900
```

If the worker is genuinely stuck on an ambiguous requirement, use Path B instead and let an operator
resolve it.

---

## Scope conflicts

A scope conflict is not a failure category — it is a refusal to start. The message names the
conflicting task and the overlapping keys:

```bash
$ hidratador start M-5002 --owner terminal-2 --lease 900
{
  "error": "resource scope reserved by M-5001: repo/api",
  "kind": "Conflict",
  "ok": false
}
```

Tasks in `IN_PROGRESS`, `BLOCKED`, and `REVIEW` all hold their scope reservation. To unblock:

```bash
# Inspect who holds what
hidratador --compact task-list | jq '.tasks[] | {id, status, scope}'

# Release the reservation
hidratador decide M-5001 retry --reason "Handing repo/api to M-5002"
# or
hidratador decide M-5001 cancel --reason "Superseded by M-5002"
```

---

## Reporting a failure explicitly

When the worker knows what went wrong, record it rather than letting it look like a lease problem:

```bash
$ hidratador fail c6be5dbd657d4b4f82572b50d852674f \
    --category dependency \
    --summary "Upstream schema missing column request_id"
{
  "category": "dependency",
  "command": "fail",
  "fingerprint": "30b9d5144fe36d3e",
  "ok": true,
  "status": "BLOCKED",
  "task_id": "M-5001"
}
```

`fail` requires an **active** session. If the session has already expired, the call is refused with
`Conflict: session is expired; expected active` — and the lease expiry has already been recorded by
`reconcile()`.

Choose the category that describes the *cause*, because the fingerprint groups by category and
summary. Repeatedly reporting the same cause with the same wording is what makes recurrence
visible:

```bash
$ hidratador --compact status | jq '.failures[] | {category, fingerprint, occurrences, summary}'
```

---

## Quick reference

| Situation | First command | Then |
|-----------|---------------|------|
| Task blocked after a crash | `hidratador reconcile` | `decide retry` then `start` |
| Task blocked on budget | `hidratador --compact status \| jq .failures` | Raise `token_budget` via the library, then `decide retry` and `start` |
| Task blocked on no progress | `hidratador --compact status \| jq .failures` | `context-add` the missing information, then `decide retry` and `start` |
| Worker hit a tool error | `hidratador fail <session> --category tool --summary "..."` | Fix the tool, then `decide retry` and `start` |
| Scope conflict | `hidratador --compact task-list \| jq '.tasks[] \| {id, status, scope}'` | `decide retry` or `decide cancel` on the holder |
| Work no longer wanted | — | `hidratador decide <id> cancel --reason "..."` |

---

## Related pages

- [CLI reference](cli-reference.md) — exact flags for every command used above
- [Architecture](architecture.md) — the lifecycle and its refusals
- [Operations](operations.md) — the stuck-task runbook
- [Context and packets](context-and-packets.md) — attaching error context
