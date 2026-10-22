# El Hidratador

**El Hidratador** is the *Context Expansion and Execution Staging Engine*. It is the bridge between
human-approved intent (the Ticket Board) and deterministic machine action (Taskrivet).

A ticket arrives **dry**: fifty words of intent. Execution needs **wet** context — a structured,
byte-budgeted, self-describing instruction that a local worker can follow without further deduction.
El Hidratador performs that hydration, stages the execution boundary, and records every step so that
acceptance stays a human decision.

> **Pipeline position:** upstream from Taskrivet, downstream from the Ticket Board.

This site documents the engine. For the project overview and install instructions, see the
[repository README](https://github.com/hamanakam1/el-hidratador/blob/main/README.md).

---

## Pipeline position

```text
                 human intent                      deterministic action
                 (approved)                        (machine)
                      |                                    |
                      v                                    v
  +-------------+  +-----------------+  +-----------------+  +-------------+
  | Ticket      |  | El Hidratador  |  | Taskrivet       |  | Repository  |
  | Board       |->| (hydration +   |->| (execution      |->| / working   |
  | (dry ticket)|  |  staging)      |  |  agent)         |  |  tree       |
  +-------------+  +-----------------+  +-----------------+  +-------------+
                          |    ^                |                   |
                          |    |                |                   |
                          v    |                v                   |
                   +------------------+  +------------------+         |
                   | Ledger (SQLite)  |  | Sandbox boundary |--------+
                   | tasks, sessions, |  | image, mounts,  |
                   | evidence, events |  | caps, limits    |
                   +------------------+  +------------------+
                          |
                          v
                   +------------------+
                   | Operator review  |  -- accept --> DONE
                   | (acceptance gate)|
                   +------------------+
```

El Hidratador never executes work itself. It produces prepared state — a hydrated packet, an
ordered manifest, a sandbox specification — and hands that state onward. A handoff is prepared
state, not permission to execute. Whether that state is executed, and whether the result is
accepted, are decisions made outside this package.

---

## The six guarantees

These hold across the whole package. They are not aspirations; each one is enforced by code that
refuses rather than degrades.

1. **The core is standard-library only.** No network calls, no shell execution, no telemetry. The
   ledger is a local SQLite file.
2. **Nothing is accepted without an explicit operator decision.** `finish()` produces `REVIEW`;
   only `decide(accept)` produces `DONE`. The acceptance gate is never bypassed.
3. **Every refusal is visible.** Conflicts, failures, expired leases, omitted context, and byte
   budget overruns are all reported explicitly, with a reason.
4. **Context is untrusted reference data, never authorization.** Attached context is quoted inside
   `--- BEGIN UNTRUSTED CONTEXT ... ---` banners and is never treated as an instruction.
5. **Eligibility is not authorization.** Routing, sandboxing, and handoff can *recommend*; none of
   them can grant. `execution_authorized` is always `false` in emitted payloads.
6. **Execution is not acceptance.** Completed work is a proposal until an operator says otherwise.
   Declared is not measured: reported token counts come from workers and are never presented as
   provider metering.

---

## Start here

Three commands, in order. This is the shortest path from an empty directory to a ledger with one
task in it.

```bash
# 1. Create the ledger (default: ~/.el-hidratador/ledger.sqlite)
hidratador init

# 2. Create a task with an objective, acceptance criteria, and resource scope
hidratador task-add M-1001 \
  --objective "Expose GET /healthz that echoes the edge request id" \
  --acceptance "GET /healthz returns 200 with the X-Request-Id header; unit test passes" \
  --scope repo/api --scope terminal-1 \
  --budget 4000

# 3. Inspect the whole ledger
hidratador status
```

Every command prints exactly one JSON object on stdout. Nothing else is written to stdout, so the
CLI composes with `jq`, pipes, and scripts without parsing prose.

For the full lifecycle — triage, lease, checkpoint, finish, accept — read the
[walkthrough](https://github.com/hamanakam1/el-hidratador/blob/main/examples/walkthrough.md).

---

## Documentation map

| Page | What it covers |
|------|----------------|
| [Architecture](architecture.md) | The five layers, module map, data model, ticket lifecycle, DAG and context algorithms, trade-offs |
| [CLI reference](cli-reference.md) | Every command, every flag, exit codes, JSON keys returned |
| [Context and packets](context-and-packets.md) | How context is attached, deduplicated, prioritised, budgeted, and omitted |
| [DAG and sandbox](dag-and-sandbox.md) | Node parsing, topological order, manifest schema, sandbox spec, boundary report |
| [GitHub sync](github-sync.md) | Observations, outbox, idempotency keys, markers, reconciliation |
| [Failure playbook](failure-playbook.md) | Every failure category, its ledger effect, and the exact recovery commands |
| [Security](security.md) | Trust boundaries, what is deliberately not done, reporting process |
| [Operations](operations.md) | Ledger location, environment variables, backup, restore, event log, stuck-task runbook |
| [Roadmap](roadmap.md) | Now / next / later phases, and an explicit not-planned list |
| [Walkthrough](https://github.com/hamanakam1/el-hidratador/blob/main/examples/walkthrough.md) | A complete runnable session, start to `DONE` |
| [Sample ticket](https://github.com/hamanakam1/el-hidratador/blob/main/examples/ticket.md) | The ticket markdown shape that the DAG parser reads |
| [Example configuration](https://github.com/hamanakam1/el-hidratador/blob/main/examples/config/hidratador.example.yaml) | Deployment shape for flags and environment variables |
| [Example sandbox spec](https://github.com/hamanakam1/el-hidratador/blob/main/examples/sandbox-spec.json) | A realistic `build_sandbox()` output |

---

## The shape of a session

```text
INBOX -> READY -> IN_PROGRESS <-> BLOCKED -> REVIEW -> ACCEPTED -> DONE
                   |                              |          |
                   |                              |          +-- only decide(accept)
                   |                              +-- decide(retry) returns to READY
                   +-- start() acquires a lease; expiry blocks the task
```

- `task-add` creates a ticket in `INBOX`.
- `triage` moves it to `READY` once scope exists.
- `start` acquires an execution lease and moves it to `IN_PROGRESS`.
- `checkpoint` records summary, evidence, next step, and cumulative tokens; it renews the lease.
- `finish` moves it to `REVIEW`.
- `decide accept` moves it through `ACCEPTED` to `DONE`. `decide retry` returns it to `READY`.
  `decide cancel` moves it to `CANCELLED`.

---

## Library use

The package is importable and the core has no runtime dependencies.

```python
from el_hidratador import Ledger
from el_hidratador.context_expander import expand_from_ledger

with Ledger("/tmp/ledger.sqlite") as ledger:
    ledger.add_task(
        "M-1001",
        objective="Expose GET /healthz that echoes the edge request id",
        acceptance="200 with the X-Request-Id header; unit test passes",
    )
    result = expand_from_ledger(ledger, "M-1001", max_bytes=8000)
    print(result["prompt"])
```

Console script: `hidratador`. Module entry point: `python -m el_hidratador`. Python 3.11 or newer.

---

## License

MIT. See [LICENSE](https://github.com/hamanakam1/el-hidratador/blob/main/LICENSE).
