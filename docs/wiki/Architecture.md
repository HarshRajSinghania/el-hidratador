# Architecture

## Layers

```text
Ticket Board ──► [ El Hidratador ] ──► Taskrivet ──► Operator review
   (dry)          hydration + staging      (wet)         (acceptance)
```

1. **Hydration** — the ticket is expanded with context, budgeted to bytes, and
   rendered into a deterministic instruction.
2. **Staging** — the expanded ticket is turned into an ordered DAG, a sandbox
   specification, and a compute routing result.
3. **Handoff** — the three are packaged for Taskrivet. The package is prepared
   state; it is not permission to execute.

## Modules

| Module | Responsibility | Network |
|--------|----------------|---------|
| `core.py` | Ledger, lifecycle, leases, budgets, failures, events, handoffs | none |
| `errors.py` | Typed error taxonomy | none |
| `context_expander.py` | Context injection, byte budgets, prompt rendering | none |
| `dag.py` | Node parsing, topological ordering, manifests | none |
| `sandbox.py` | Sandbox specifications and the optional Docker adapter | adapter only |
| `hardware_router.py` | Workload classification and eligibility | none |
| `github_sync.py` | Observations, outbox, reconciliation | `gh` CLI only |
| `dashboard.py` | Local dashboard preview | loopback HTTP only |
| `tickets.py` | Portable file-backed ticket storage | none |
| `cli.py` | JSON-first command line interface | none |

## Ledger schema

| Table | Purpose |
|-------|---------|
| `tickets` | The work item, its scope, budget, and lifecycle state |
| `sessions` | Execution leases with owners, expiry, and reported tokens |
| `checkpoints` | Evidence recorded at a point in a session |
| `contexts` | Content-addressed context bodies |
| `task_context` | Which context is attached to which task, with priority and expiry |
| `failures` | Fingerprinted failures, grouped for recurrence analysis |
| `profiles` | Declared compute profiles and their validity window |
| `events` | Append-only audit log |
| `handoffs` | Recorded handoff payloads |
| `observations` | Read-only GitHub observations |
| `outbox` | Queued, idempotent GitHub writes |
| `meta` | Schema version |

Migrations are additive and idempotent. The schema version lives in `meta`.

## Lifecycle

```text
INBOX → READY → IN_PROGRESS ⇄ BLOCKED → REVIEW → ACCEPTED → DONE
```

- `start()` grants a lease and reserves the ticket's resource scope.
- `checkpoint()` demands summary, evidence, next step, and cumulative tokens.
- Three checkpoints with identical evidence block the task as `no_progress`.
- Budgets are cumulative and survive retries.
- `finish()` produces `REVIEW`. Only `decide(accept)` produces `DONE`.

## Determinism

The same ticket always produces the same prompt and the same manifest hash.
That is what makes caching, diffing, and evidence hashes meaningful.
