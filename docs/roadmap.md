# Roadmap

This roadmap is written as **observable outcomes**, not as intentions. Each item says what will be
true when it is done, and how you can tell.

Anything that has not been verified against running code is marked **unverified**. Everything in the
"Now" section that is described as existing has been read from the source at the time of writing.

---

## Now — shipped and documented

These behaviours exist in `0.1.0` and are described in the pages linked below.

| Outcome | Where it lives |
|---------|----------------|
| A ticket's lifecycle is enforced by a local SQLite ledger, with every state change on an append-only event log | [Architecture](architecture.md) |
| A ticket cannot reach `DONE` without an explicit `decide accept` | [Architecture](architecture.md) |
| A lease prevents two workers from holding the same scope keys at once, and an expired lease blocks the task automatically | [Failure playbook](failure-playbook.md) |
| Context is attached, deduplicated by content hash, ordered by priority, byte-budgeted, and every omission is reported by hash and reason | [Context and packets](context-and-packets.md) |
| Attached context is wrapped in fixed untrusted banners and the packet carries an explicit trust statement | [Context and packets](context-and-packets.md) |
| A ticket body is parsed into a deterministic, cycle-checked execution DAG with a hashed manifest | [DAG and sandbox](dag-and-sandbox.md) |
| A sandbox boundary is described as reviewable data with a spec hash, and applying it is a dry run by default | [DAG and sandbox](dag-and-sandbox.md) |
| GitHub writes are idempotent, carry a marker, and reconcile against existing comments before sending | [GitHub sync](github-sync.md) |
| The dashboard adapter refuses anything that is not loopback HTTP | [Security](security.md) |
| Every CLI command emits exactly one JSON object and a documented exit code | [CLI reference](cli-reference.md) |
| Tickets can be exported to a portable, diffable file tree | [Operations](operations.md) |

---

## Next — the next set of changes

Each item names the outcome that proves it is done.

### Close the gap between the library and the CLI

Several library capabilities are not reachable from the command line today. The outcome is that an
operator can do everything the library can do without writing Python.

- `Ledger.update_task()` becomes a `task-update` command. **Observable:** `hidratador task-update
  M-1001 --budget 16000` changes the ticket's budget, and a task that was blocked on budget can be
  retried and started without a Python script.
- Sandbox lifecycle becomes a command. **Observable:** `hidratador sandbox-apply --id <task> --
  workdir <path>` prints the exact `docker run` argv by default and only creates the container when
  `--apply` is passed; `hidratador sandbox-teardown --name <container>` removes it.
- Read-only views for records the ledger already holds. **Observable:** `hidratador checkpoints
  <session>`, `hidratador failures [--task <id>]`, and `hidratador handoffs <id>` return those
  records as JSON.
- The GitHub adapter's own state becomes visible. **Observable:** `hidratador github-status
  [--repo owner/name]` reports observation counts and outbox counts by state.
- The dashboard health probe becomes a command. **Observable:** `hidratador dashboard-health --url
  <url>` returns `{"reachable": true, ...}` without raising.
- The local topology report becomes a command. **Observable:** `hidratador topology` prints the
  platform, machine, and Python version the package sees.

### Make the DAG parser configurable

Task lines are already read from the `## Tasks` section when the body has one, and acceptance
criteria are never mistaken for work. What is left:

- The dependency keyword list is narrowed, or a task that mentions `after` without ids is left
  alone. **Observable:** a task titled *"Wait after the cache warms"* keeps its title and has an
  empty `depends_on`.
- Section names become configurable. **Observable:** `build_dag(..., sections={"tasks": "Work
  items"})` reads the task list from a `## Work items` heading.
- `Dag.ready_nodes()` and `parallel_groups()` become CLI-visible. **Observable:** `hidratador dag
  <id> --ready` lists the nodes that could start now.

### Complete the observation vocabulary

`poll()` currently produces `issues`, `comments`, `pulls`, and `releases`. The other kinds in
`OBSERVATION_KINDS` are accepted by `record_observation` but never produced, and two actions in
`ACTIONS` are never emitted.

- Workflow runs are polled. **Observable:** a failed workflow run appears as a `runs` observation
  with the action `investigate_failed_check`.
- The remaining observation kinds become reachable. **Observable:** `review_comments`, `commits`,
  and `events` are produced by `poll()` or by a dedicated command, and the action
  `inspect_repository_activity` is emitted for repository-level activity.
- Observations can be attached to a ticket. **Observable:** `hidratador context-add <id> --from-
  observation <hash>` brings an observed item into a packet as untrusted context.

### Make the file-backed store round-trip

Export is one-directional today: ledger to files, never back.

- Tickets can be imported from a file tree. **Observable:** `hidratador import --dir .hidratador`
  creates or updates tickets from the markdown files, honouring `seed_key` idempotency.
- Evidence records are written by the CLI. **Observable:** after `hidratador finish`, an evidence
  file exists under `.hidratador/evidence/<id>/finish.json`.
- The index is rebuilt on demand. **Observable:** `hidratador export --rebuild-index` regenerates
  `index.json` without rewriting the ticket files.

### Prove the boundaries with tests

The boundaries are documented; they should be executable.

- A test suite that asserts the core imports no network or process-spawning module. **Observable:**
  the check runs in CI and fails if a socket, subprocess, or HTTP import appears in the core.
- A test suite that asserts the dashboard adapter refuses every non-loopback host and every
  credential-bearing URL. **Observable:** the test enumerates the refusal messages.
- A test suite that asserts the GitHub publisher never double-posts. **Observable:** the test
  simulates a comment that already carries the marker and asserts the state becomes `reconciled`.

---

## Later — plausible directions

Unverified. These are directions, not commitments, and none of them are on a schedule.

- **Ledger sharding.** Splitting one ledger per project instead of one global ledger.
  **Unverified:** the current conflict detection queries the whole `tickets` table, so sharding would
  need an explicit scope-namespace decision.
- **A richer sandbox profile system.** Named sandbox profiles with their own images, mount sets, and
  limits, stored in the ledger. **Unverified:** `build_sandbox()` currently takes every parameter
  positionally or by keyword with hard-coded defaults.
- **Attaching a profile to a task.** A ticket could name the compute profile it expects, and routing
  could compare that against the declared profile set. **Unverified:** `Ledger.route()` and
  `hardware_router.evaluate()` currently operate on separate target models.
- **DAG state persisted across attempts.** The manifest's node completion state could be recorded so
  a retry resumes at the right node rather than at the first one. **Unverified:** the manifest is
  regenerated from the ticket description on every call, and `done` flags come only from checkbox
  state in the body.
- **Signed handoffs.** A handoff payload could be signed so the execution layer can verify that the
  manifest it received is the manifest that was staged. **Unverified:** `manifest_hash` and
  `spec_hash` exist today but are plain hashes with no key management. A handoff is prepared state,
  not permission to execute, and a signature would not change that.
- **An event-stream interface.** A `tail`-style follower for the events table. **Unverified:** the
  events table is polled through `events(after=N, limit=500)`.

---

## Not planned

These are decisions, not omissions. Each one would break a property the package currently holds.

| Not planned | Why |
|-------------|-----|
| **Automatic acceptance** | No timeout, heuristic, or score may move a task to `DONE`. Only `decide(accept)` does. |
| **Automatic execution** | The package prepares state. It does not start work. `execution_authorized` is `false` in every emitted payload. |
| **Cloud dispatch** | Dispatching work to a remote or paid provider would require metering and authorisation this package does not have. Routing reports eligibility; it never authorises. |
| **A multi-tenant ledger** | One ledger, one operator, one trust domain. Sharing one ledger across tenants would break the file-permission model and make scope keys ambiguous. |
| **Credential storage** | Tokens are never read, stored, or logged. The `gh` CLI owns authentication. |
| **Telemetry of any kind** | No usage analytics, no crash reporting, no phone-home. `measured_cash_cost` and `measured_token_savings` stay `null` because the package cannot measure them. |
| **A network path in the core** | The core is standard-library only and reaches no network. The two network-capable adapters are optional, narrow, and explicit. |
| **Treating context as instruction** | Attached context is reference data. It is never authorisation and never a command. |
| **Deleting audit history** | Events and failures are append-only. Compaction is a backup concern, not an in-place deletion. |
| **A plugin or extension system** | The core boundary is the point. A plugin loader would make the dependency surface unbounded. |
| **Silent truncation** | If context does not fit, it is reported as omitted with a hash and a reason. There is no quiet drop path. |

---

## Related pages

- [Architecture](architecture.md) — the current design
- [CLI reference](cli-reference.md) — what the command surface covers today
- [Failure playbook](failure-playbook.md) — the behaviour that must not regress
- [Security](security.md) — the boundaries that constrain the roadmap
