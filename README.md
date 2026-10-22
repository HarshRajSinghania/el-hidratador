# El Hidratador

```text
███████╗██╗  ██╗██╗   ██╗███████╗██████╗ ██╗   ██╗██╗  ██╗ ██████╗ ██████╗ ██████╗ ██╗   ██╗
██╔════╝██║  ██║██║   ██║██╔════╝██╔══██╗██║   ██║██║  ██║██╔═══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝
███████╗███████║██║   ██║███████╗██████╔╝██║   ██║███████║██║   ██║██████╔╝██████╔╝██║  ██║ ╚████╔╝
╚════██║╚════██║██║   ██║╚════██║██╔═══╝ ██║   ██║██╔════╝██║   ██║██╔══██╗██╔══██╗██║  ██║  ╚██╔╝
███████║     ██║╚██████╔╝███████║██║     ███████╗██║     ██║╚██████╔╝██║  ██║██████╔╝██║  ██║   ██║
╚══════╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝     ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝   ╚═╝
```

**The Context Expansion and Execution Staging Engine.**

El Hidratador is the bridge between human-approved intent and deterministic machine
action. It turns a *dry* semantic ticket — fifty words of intent — into *wet* execution
state: expanded context, an ordered execution DAG, a locked sandbox boundary, and a
routed compute profile.

> **Pipeline position:** downstream from the Ticket Board, upstream from Taskrivet.

```text
Ticket Board ──► [ El Hidratador ] ──► Taskrivet ──► Operator review
   (dry)          hydration + staging      (wet)         (acceptance)
```

---

## Badges

[![CI](https://github.com/hamanakam1/el-hidratador/actions/workflows/ci.yml/badge.svg)](https://github.com/hamanakam1/el-hidratador/actions/workflows/ci.yml)
[![CodeQL](https://github.com/hamanakam1/el-hidratador/actions/workflows/codeql.yml/badge.svg)](https://github.com/hamanakam1/el-hidratador/actions/workflows/codeql.yml)
[![Scorecard](https://github.com/hamanakam1/el-hidratador/actions/workflows/scorecard.yml/badge.svg)](https://github.com/hamanakam1/el-hidratador/actions/workflows/scorecard.yml)
[![Security Scan](https://github.com/hamanakam1/el-hidratador/actions/workflows/security-scan.yml/badge.svg)](https://github.com/hamanakam1/el-hidratador/actions/workflows/security-scan.yml)
[![PyPI](https://img.shields.io/pypi/v/el-hidratador.svg)](https://pypi.org/project/el-hidratador/)
[![Python](https://img.shields.io/pypi/pyversions/el-hidratador.svg)](https://pypi.org/project/el-hidratador/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![Typed](https://img.shields.io/badge/typing-mypy-blue.svg)](pyproject.toml)

---

## Why it exists

Autonomous execution fails in three predictable ways, and all three are context
problems wearing a costume:

1. **The worker starts with fifty words and a repository of four million.**
2. **Two workers touch the same resource and neither knows about the other.**
3. **Work is declared complete by the worker that performed it.**

El Hidratador is built around refusing those three failures:

| Failure | What El Hidratador does |
|---------|--------------------------|
| Underspecified execution | Expands a ticket into a byte-budgeted, self-describing instruction |
| Resource collision | Grants execution leases and refuses overlapping scopes |
| Self-acceptance | Separates *finished* from *accepted*; only an operator accepts |

---

## The six guarantees

These hold for every code path in this repository:

1. **The core is standard library only.** No network, no shell execution, no telemetry.
2. **Nothing is accepted implicitly.** `finish()` creates `REVIEW`; only
   `decide(accept)` creates `DONE`.
3. **Eligibility is not authorization.** Routing can recommend a target and can
   never authorize one.
4. **Declared is not measured.** Token counts are reported by workers, never metered
   by a provider. `measured_cash_cost` is `null` on purpose.
5. **Context is untrusted reference data.** Attached context is quoted inside
   explicit banners and never treated as an instruction.
6. **Every refusal is visible.** Conflicts, budget stops, stagnation, and omitted
   context are reported, not swallowed.

---

## Install

```bash
# From a checkout
python3 -m pip install -e .

# Or run without installing
python3 -m el_hidratador --help
```

Python 3.11 or newer. No runtime dependencies. The optional adapters use the `gh`
and `docker` command line tools, and only when you invoke them.

---

## Quick start

```bash
# 1. Create the ledger
hidratador init

# 2. Describe the work
hidratador task-add M-1001 \
  --objective "Implement JWT-based authentication" \
  --acceptance "Issuance, refresh rotation, and revocation all work" \
  --scope repo/api --scope repo/auth \
  --tags security,auth \
  --budget 8000

# 3. Triage it into the ready queue
hidratador triage M-1001

# 4. Take the lease
hidratador start M-1001 --owner terminal-1 --lease 900
# → {"session_id": "…", "lease_until_iso": "…"}

# 5. Record evidence as you go
hidratador checkpoint <session-id> \
  --summary "Implemented token issuance" \
  --evidence "diff 4f2a1c; POST /api/auth/login returns an access+refresh pair" \
  --next "Refresh rotation" \
  --tokens 1200

# 6. Request review
hidratador finish <session-id> --evidence "All endpoints tested; diff 4f2a1c"

# 7. An operator accepts
hidratador decide M-1001 accept --reason "Reviewed the diff and the tests"
# → {"status": "DONE"}
```

Every command prints exactly one JSON object. Nothing else is written to stdout.

---

## Core concepts

| Concept | Description |
|---------|-------------|
| **Bounded context** | Every ticket carries an objective, acceptance criteria, scope keys, and a token budget |
| **Explicit ownership** | `start()` acquires a lease; an expired lease blocks the task until reconciliation |
| **Resource scope** | Tickets reserve resource keys; two tickets with overlapping scopes cannot run at once |
| **Evidence at every step** | `checkpoint()` requires summary, evidence, next step, and cumulative tokens |
| **Cumulative budget** | Token budgets survive retries; tokens never decrease |
| **Stagnation detection** | Three checkpoints with identical evidence block the task as `no_progress` |
| **Acceptance ≠ execution** | `finish()` → `REVIEW` → operator `decide(accept)` → `DONE` |
| **Failure fingerprints** | `sha256(category:summary)[:16]` groups recurring failures |

### Lifecycle

```text
INBOX → READY → IN_PROGRESS ⇄ BLOCKED → REVIEW → ACCEPTED → DONE
             ↑__________|___________|
                 retry (tokens preserved)
```

| Station | Entered when | Left when |
|---------|--------------|-----------|
| `INBOX` | The ticket is created | It is triaged |
| `READY` | Scope and budget are defined | A lease is acquired |
| `IN_PROGRESS` | `start()` succeeded | A checkpoint, a failure, or lease expiry |
| `BLOCKED` | Lease expired, budget exhausted, no progress, or an explicit failure | `decide(retry)` or cancellation |
| `REVIEW` | `finish()` was called with evidence | An operator decides |
| `ACCEPTED` | `decide(accept)` | Immediately transitions to `DONE` |
| `DONE` | Accepted work | Immutable |

---

## Architecture

```text
                    ┌───────────────────────────────────────────┐
   Ticket Board ──► │  core.Ledger  (SQLite, WAL, event log)    │
   (dry intent)     │  tasks · sessions · checkpoints · failures │
                    └───────────────┬───────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
 context_expander              dag.build_dag              hardware_router
 budgeted prompt,            ordered nodes,              eligibility only,
 untrusted context           manifest, waves             never authorization
        │                           │                           │
        └───────────────┬───────────┴───────────┬───────────────┘
                        ▼                       ▼
                 sandbox.build_sandbox    github_sync
                 read-only root,          observations + reconciled
                 scoped mounts           outbox
                        │                       │
                        └───────────┬───────────┘
                                    ▼
                         handoff → Taskrivet
                    (prepared state, not permission)
```

### Module map

| Module | Responsibility | Network |
|--------|----------------|---------|
| `core.py` | Ledger, lifecycle, leases, budgets, failures, events, handoffs | none |
| `errors.py` | Typed error taxonomy | none |
| `context_expander.py` | Context injection, byte budgets, prompt rendering | none |
| `dag.py` | Node parsing, topological ordering, manifests | none |
| `sandbox.py` | Sandbox specifications and the optional Docker adapter | adapter only |
| `hardware_router.py` | Compute classification and eligibility | none |
| `github_sync.py` | Observations, outbox, reconciliation | `gh` CLI only |
| `dashboard.py` | Local dashboard preview | loopback HTTP only |
| `tickets.py` | Portable file-backed ticket storage | none |
| `cli.py` | JSON-first command line interface | none |

---

## Security boundaries

| Boundary | Rule |
|----------|------|
| **Core** | No network, no shell execution, no telemetry, standard library only |
| **Adapters** | Declare the supported version, permission model, and cancellation semantics |
| **Sandbox** | Read-only root filesystem, no network by default, all capabilities dropped |
| **Dashboard** | HTTP only, loopback only, no redirects, 8 MiB cap, 10 s timeout, no credentials in URL |
| **GitHub** | `gh` CLI only, no token ever read by this package, 30 s timeout, 16 MiB cap |
| **Secrets** | Never in the repository; injected through the environment at deploy time |

Local state is created with restrictive permissions: the ledger directory is `0700`
and the ledger file is `0600`.

See [SECURITY.md](SECURITY.md) for the reporting process and
[`docs/security.md`](docs/security.md) for the full model.

---

## Documentation

| Page | What it covers |
|------|----------------|
| [docs/index.md](docs/index.md) | Documentation home and reading order |
| [docs/architecture.md](docs/architecture.md) | Layers, data model, end-to-end sequence |
| [docs/cli-reference.md](docs/cli-reference.md) | Every command, flag, and output key |
| [docs/context-and-packets.md](docs/context-and-packets.md) | Budgeting, priority, omission, untrusted context |
| [docs/dag-and-sandbox.md](docs/dag-and-sandbox.md) | Node parsing, ordering, manifest, sandbox spec |
| [docs/github-sync.md](docs/github-sync.md) | Observations, outbox, idempotency, reconciliation |
| [docs/failure-playbook.md](docs/failure-playbook.md) | Every failure category and its recovery path |
| [docs/operations.md](docs/operations.md) | Day-to-day operation, backup, runbooks |
| [docs/security.md](docs/security.md) | Trust model and boundaries |
| [docs/roadmap.md](docs/roadmap.md) | What is next, and what is explicitly not planned |
| [examples/walkthrough.md](examples/walkthrough.md) | A complete runnable session |

---

## Development

```bash
python3 -m pip install -e ".[dev]"

# Tests
python3 -m unittest discover -s tests -v

# Lint, format, types
ruff check el_hidratador/
ruff format --check el_hidratador/
mypy el_hidratador/

# Everything the CI runs
make check
```

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first — the
acceptance rules there are the same rules the code follows.

---

## Repository features

| Feature | Where |
|---------|-------|
| Issue forms (bug, feature, question, docs) | [New issue](https://github.com/hamanakam1/el-hidratador/issues/new/choose) |
| Discussions | [github.com/hamanakam1/el-hidratador/discussions](https://github.com/hamanakam1/el-hidratador/discussions) |
| Wiki | [github.com/hamanakam1/el-hidratador/wiki](https://github.com/hamanakam1/el-hidratador/wiki) |
| Roadmap | [docs/roadmap.md](docs/roadmap.md) and the `roadmap` label |
| Releases | [github.com/hamanakam1/el-hidratador/releases](https://github.com/hamanakam1/el-hidratador/releases) |
| Security advisories | [SECURITY.md](SECURITY.md) |
| Published documentation | [hamanakam1.github.io/el-hidratador](https://hamanakam1.github.io/el-hidratador/) |

---

## License

MIT — see [LICENSE](LICENSE). Author: Michael Hamanaka.
