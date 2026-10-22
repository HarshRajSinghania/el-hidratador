# Architecture

El Hidratador is organised in five layers. Each layer has one job, and the boundaries between them
are where the safety properties live.

---

## The five layers

```text
1. Ticket Board     human-approved intent          dry ticket
        |            (objective, acceptance, scope, budget)
        v
2. Hydration        context expansion               wet packet
        |            (byte-budgeted, untrusted context quoted, prompt rendered)
        v
3. Staging          execution DAG + sandbox         manifest + spec
        |            (ordered nodes, files, tests, image, mounts, caps, limits)
        v
4. Execution        Taskrivet (outside this package)  container
        |            (runs inside the staged boundary)
        v
5. Acceptance       operator review                 DONE
                     (finish() -> REVIEW -> decide(accept) -> DONE)

```

**Layer 1 — Ticket Board.** A ticket is semantic: what to build, how it is judged complete, which
resource keys it touches, how many tokens it may spend. El Hidratador does not author tickets; it
consumes them.

**Layer 2 — Hydration.** A dry ticket is expanded into a packet: the mandatory structure (objective,
acceptance, scope, tags, files, tests, latest checkpoint) plus any attached context, all inside a
byte budget. Context is untrusted reference data, never authorization: attached bodies are quoted
inside explicit untrusted banners and carry no authority.

**Layer 3 — Staging.** The ticket's own structure is parsed into an ordered execution graph, and a
sandbox specification is produced as pure data — image, mounts, resource limits, dropped
capabilities, environment. Both are reviewable and hashable before anything is created.

**Layer 4 — Execution.** Performed by Taskrivet, outside this package. El Hidratador hands over a
prepared payload and never authorises execution. A handoff is prepared state, not permission to
execute.

**Layer 5 — Acceptance.** Work returns to the ledger as `REVIEW`. Only an explicit operator
decision moves it to `DONE`.

---

## Module map

| Module | Responsibility | Network | Shell |
|--------|----------------|---------|-------|
| `core.py` | `Ledger`: tasks, sessions, checkpoints, contexts, failures, profiles, events, handoffs | no | no |
| `errors.py` | `HidratadorError` and the six typed refusals | no | no |
| `context_expander.py` | `build_packet`, `render_prompt`, `expand_from_ledger`, `estimate_tokens`, `split_budget`, `dedupe_context`, `summarize_packet` | no | no |
| `dag.py` | `build_dag`, `parse_tasks`, `parse_files`, `parse_tests`, `manifest`, `handoff_payload`, `parallel_groups`, `summarize`, `Node`, `Dag` | no | no |
| `sandbox.py` | `build_sandbox`, `docker_command`, `apply_sandbox`, `teardown_sandbox`, `boundary_report` | no | `docker` (optional adapter) |
| `hardware_router.py` | `Target`, `RouteResult`, `classify`, `evaluate`, `dispatch_plan`, `default_targets`, `local_topology` | no | no |
| `github_sync.py` | `GitHubSync`: `record_observation`, `observations`, `poll`, `enqueue`, `pending`, `outbox`, `publish`, `status`, `body_hash`, `marker` | `gh` only | `gh` (optional adapter) |
| `dashboard.py` | `validate_url`, `fetch`, `preview`, `health` | loopback HTTP only | no |
| `tickets.py` | `TicketStore`, `render_ticket`, `render_front_matter`, `parse_front_matter` | no | no |
| `cli.py` | JSON-first CLI; the `hidratador` console script | delegates | delegates |

The core boundary — `core.py`, `errors.py`, `context_expander.py`, `dag.py`, `hardware_router.py`,
`tickets.py` — imports nothing outside the standard library and performs no I/O beyond the local
SQLite file and the local filesystem.

---

## Data model

All state lives in one SQLite database opened in WAL mode with `PRAGMA foreign_keys=ON`. Schema
version is `3`; migrations are additive and idempotent.

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `meta` | Schema version and other key/value bookkeeping | `key` (PK), `value` |
| `tickets` | The work items and their hydration state | `id` (PK), `title`, `objective`, `acceptance`, `kind`, `scope`, `status`, `priority`, `token_budget`, `tags`, `depends_on`, `blocks`, `owner`, `seed_key`, `description`, `acceptance_criteria`, `created_at`, `updated_at` |
| `sessions` | Execution leases on a task | `id` (PK), `task_id` → `tickets.id` (cascade), `owner`, `status`, `lease_until`, `tokens`, `progress`, `stagnant`, `created`, `error`, `warning`, `stop_reason` |
| `checkpoints` | Evidence recorded during a session | `id` (autoincrement), `session_id` → `sessions.id` (cascade), `summary`, `evidence`, `next_step`, `tokens`, `created`, `evidence_hash` |
| `contexts` | Content-addressed context bodies | `hash` (PK), `body` |
| `task_context` | Which context blob is attached to which task, at what priority and expiry | `task_id` + `hash` (composite PK), `source`, `priority`, `expires` |
| `failures` | Recorded failures, grouped by fingerprint | `id` (autoincrement), `task_id` → `tickets.id` (cascade), `session_id` → `sessions.id` (set null), `category`, `fingerprint`, `summary`, `created` |
| `profiles` | Declared compute profiles | `id` (PK), `kinds`, `context_limit`, `cost`, `verified_until` |
| `events` | Append-only audit log | `seq` (autoincrement), `type`, `task_id`, `data` (JSON), `created` |
| `handoffs` | Prepared handoff payloads | `id` (PK), `task_id` → `tickets.id` (cascade), `session_id` → `sessions.id` (set null), `manifest` (JSON), `packet` (JSON), `created` |
| `observations` | Declared in the core schema; reserved for observation records | `repo` + `kind` + `identity` (composite PK), `revision`, `observed`, `summary`, `action`, `url` |
| `outbox` | Declared in the core schema; reserved for queued writes | `repo` + `issue` + `key` (composite PK), `body_hash`, `state`, `url`, `created` |

Two constraints worth calling out:

- `tickets_seed_key` is a **partial unique index** on `seed_key` where `seed_key <> ''`. Re-adding a
  task with the same seed key returns the original task id and `"created": false` — the operation is
  idempotent, not duplicated.
- `one_active_session` is a **partial unique index** on `task_id` where `status = 'active'`. A task
  can never hold two live leases, even if two workers race for it.

The `observations` and `outbox` tables in the core ledger are created by the schema but are not
written by the core. The GitHub adapter keeps its own database (see
[GitHub sync](github-sync.md)).

---

## The lifecycle of a ticket

```text
task-add
   |  creates a ticket, status = INBOX, scope defaults to [task_id]
   v
triage
   |  requires status INBOX and a non-empty scope -> READY
   v
start --owner terminal-1 --lease 900
   |  reconciles stale leases, checks cumulative budget, checks scope overlap,
   |  inserts an active session, sets lease_until = now + 900 -> IN_PROGRESS
   v
checkpoint --summary --evidence --next --tokens
   |  requires an active, unexpired lease
   |  requires tokens to be non-decreasing
   |  renews lease_until = now + lease_seconds
   |  computes the evidence hash; 3 identical hashes in a row -> BLOCKED (no_progress)
   |  cumulative tokens across attempts >= token_budget -> BLOCKED (budget)
   v
finish --evidence
   |  requires at least one checkpoint on this session -> REVIEW
   v
decide accept --reason "..."
   |  ACCEPTED, then DONE, with two audit events
   v
DONE
```

Alternatives from `BLOCKED` and `REVIEW`:

- `decide retry --reason "..."` → `READY`. Cumulative tokens are preserved, so the next `start`
  continues against the same budget.
- `decide cancel --reason "..."` → `CANCELLED`.

Refusals along the way:

| Operation | Refusal condition | Error |
|-----------|-------------------|-------|
| `triage` | status is not `INBOX` | `Conflict` |
| `start` | status is not `READY` or `INBOX` | `Conflict` |
| `start` | cumulative tokens >= `token_budget` | `BudgetExceeded` |
| `start` | another live task holds an overlapping scope key | `Conflict` |
| `start` | the task already has an active session | `Conflict` |
| `checkpoint` | session inactive or lease expired | `LeaseExpired` |
| `checkpoint` | `tokens` lower than the previous count | `Conflict` |
| `finish` | no checkpoint recorded on the session | `Conflict` |
| `decide` | the decision is not legal from the current status | `Conflict` |

---

## The DAG algorithm

`build_dag(task_id, markdown, ticket_dependencies)` produces a deterministic, acyclic graph.

1. **Parse tasks.** Every line matching `- [ ]` / `- [x]` / `- [X]` becomes a node. A trailing
   `depends on A, B`, `requires A`, or `after A` clause is stripped from the title and recorded as
   node dependencies.
2. **Parse files and tests.** File paths come from a `## Files Created` section; test paths come
   from a `## Tests` section, falling back to the `Files Created` entries whose path contains
   `test`.
3. **Add a prerequisites root.** If the ticket has ticket-level dependencies, a node with id
   `{task_id}:prerequisites` and `source: "ticket-dependencies"` is created, carrying those
   dependency ids. It sorts first in the topological order, and every task-level node depends on
   it, so a ticket with unmet prerequisites has no ready task work.
4. **Attach artifacts.** A file or test is attached to a node when its path appears (case
   insensitively) in that node's title. Anything left over is attached to the last node.
5. **Topologically order.** Kahn's algorithm with deterministic tie-breaking — the ready set is
   sorted by node id at every step. A dependency that names a node outside this graph (another
   ticket) is kept as an external reference and does not constrain ordering.
6. **Reject cycles.** If not every node is ordered, a `Conflict` is raised naming the unresolved
   nodes. Cycles are never silently reordered.
7. **Fallback.** If there are no nodes at all, a single node `{task_id}:single` titled
   "Execute the ticket objective as one step" is created.

See [DAG and sandbox](dag-and-sandbox.md) for the parsing grammar and the manifest schema.

---

## The context expansion pipeline

```text
attached blobs                 contexts + task_context (content-addressed)
        |
        |  ordered by priority DESC, hash
        v
mandatory structure             objective, acceptance, acceptance criteria, scope,
        |                       tags, files, tests, latest checkpoint, trust note
        v
size check                      does the mandatory structure fit max_bytes?
        |                       no -> refuse (Conflict / ValidationError)
        v
add context, re-measure         fits? keep. does not fit? pop and record as omitted
        |
        v
packet + prompt + omission list
```

Two budget implementations exist and they are not identical:

- `Ledger.pack()` measures the **JSON encoding of the packet only**.
- `context_expander.build_packet()` measures the **JSON encoding plus the rendered prompt**.

Both add context in priority order and both report every omission by hash and reason. See
[Context and packets](context-and-packets.md).

---

## The sandbox boundary

`build_sandbox()` produces a specification, not a container. The specification is a plain
dictionary with a `spec_hash`, so it can be reviewed, diffed, and signed off before anything runs.

Defaults:

| Field | Default |
|-------|---------|
| `image` | `python:3.12-slim` |
| `workdir` | required, must be an absolute path |
| `mounts` | `[{source: workdir, target: /workspace, mode: rw, purpose: working tree}]` |
| `read_only_root` | `true` |
| `network` | `none` |
| `resources` | `{memory: 4g, cpus: 2.0, pids: 512}` |
| `environment` | `{PYTHONUNBUFFERED: 1, HIDRATADOR_TASK_ID: <task id>}` |
| `cap_drop` | `["ALL"]` |
| `security_opt` | `["no-new-privileges:true"]` |
| `command` | `["sleep", "infinity"]` |
| `created` | `false` |
| `provenance` | `"declared staging boundary; not a running container"` |

`apply_sandbox()` defaults to `dry_run=True` and returns the rendered argv without touching Docker.
Turning it off shells out to the `docker` CLI with a fixed argv, a timeout, and a minimal
environment (`PATH` and `HOME` only — no credential environment is inherited).

---

## Decisions and trade-offs

| Decision | Why | What it costs |
|----------|-----|---------------|
| SQLite with WAL, `foreign_keys=ON` | A single local file is inspectable with standard tools, survives process restarts, and needs no server. WAL keeps readers from blocking the writer. | Concurrent writers serialise; the ledger is a single-writer coordination point by design. |
| Leases rather than heartbeats | An explicit `lease_until` timestamp is a fact stored in the database. A crashed worker's lease expires on its own and is detected by `reconcile()`. No daemon has to watch it. | A worker that stalls without checking in still loses its lease. Lease renewal happens as a side effect of `checkpoint()`. |
| Cumulative token budgets across attempts | A retry that resets the counter would let a task consume an unbounded total. The cumulative count is the number that enforces the cap. | A retry after a partial attempt starts with less headroom. `decide(retry)` never resets the count. |
| Byte budgets rather than token budgets | Token counts depend on a provider's tokenizer, which this package cannot know. Bytes are exact, measurable, and enforce a real limit. | The byte budget does not directly bound a provider's tokenisation; a `token_estimate` is reported alongside as a character-based heuristic. |
| Content-addressed context | Identical context blobs are stored once and deduplicated by construction. A hash identifies context in reports without exposing its body. | Re-attaching the same body with a different priority updates the link rather than creating a second copy. |
| Omission reported, never silent | A context blob that does not fit is dropped, but it is reported by hash, source, and reason. | The operator must notice the omission list; the packet alone does not show what is missing. |
| Partial unique indexes for idempotency | `seed_key` and one-active-session are enforced by the database, not by application logic, so races cannot produce duplicates. | Seed keys must be chosen by the caller; the package cannot infer them. |
| Additive idempotent migrations | The schema version is stored in `meta`; migrations only add columns and never rewrite data. | Each migration is small, which means several may need to run for an old ledger. |
| Deterministic ordering everywhere | Node order, prompt layout, manifest hash, and spec hash are all reproducible, so two runs of the same ticket can be diffed. | Determinism rules out "smart" ordering that could optimise for runtime. |
| Acceptance never implied | `finish()` alone cannot produce `DONE`. The gate is the point of the system. | Work can sit in `REVIEW` indefinitely without an operator. |

---

## Related pages

- [CLI reference](cli-reference.md) — command surface
- [Context and packets](context-and-packets.md) — hydration in detail
- [DAG and sandbox](dag-and-sandbox.md) — staging in detail
- [Failure playbook](failure-playbook.md) — what to do when the lifecycle refuses
- [Operations](operations.md) — running the ledger day to day
