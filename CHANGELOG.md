# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. Open an issue or a discussion before starting work on something
large — the `roadmap` label tracks what is already planned.

## [0.1.0] — 2026-10-22

The first release. It establishes the pipeline position of El Hidratador
between the Ticket Board and Taskrivet, and nothing else.

### Added

**Core ledger** (`el_hidratador/core.py`)

- SQLite ledger with WAL mode, foreign keys enabled, and schema version 3
- Additive, idempotent schema migrations
- Ticket lifecycle with eight stations: `INBOX`, `READY`, `IN_PROGRESS`,
  `BLOCKED`, `REVIEW`, `ACCEPTED`, `DONE`, `CANCELLED`
- Execution leases with expiry, reconciliation, and automatic blocking
- Resource scope reservations that refuse overlapping concurrent work
- Cumulative token budgets that survive retries and never decrease
- Stagnation detection: three checkpoints with identical evidence block the
  task as `no_progress`
- Fingerprinted failures (`sha256(category:summary)[:16]`) grouped for
  recurrence analysis
- Context attachment that is content-addressed, deduplicated, and expirable
- Byte-budgeted packet assembly that reports everything it omits
- Compute profile declarations and eligibility-only routing
- Append-only event log and recorded handoff payloads

**Context expansion** (`el_hidratador/context_expander.py`)

- Deterministic prompt rendering with a stable output contract
- Untrusted-context banners around every attached body
- Exact byte budgets with explicit omission reporting
- Character-based token estimation, labelled as an estimate

**Execution DAG** (`el_hidratador/dag.py`)

- Checklist and file-section parsing for ticket bodies
- Deterministic topological ordering with cycle detection
- Parallel wave grouping
- Execution manifests that never claim authorization

**Sandbox staging** (`el_hidratador/sandbox.py`)

- Pure sandbox specifications: image, mounts, resources, capabilities
- Read-only root filesystem, no network by default, all capabilities dropped
- `docker run` argv rendering and a dry-run-first apply path

**Hardware routing** (`el_hidratador/hardware_router.py`)

- Workload classification and target eligibility evaluation
- Cost as a hard gate; a paid target is never eligible for autonomous dispatch
- Dispatch plans that never authorize execution

**GitHub sync** (`el_hidratador/github_sync.py`)

- Read-only observations with an eight-kind vocabulary and a six-action
  recommendation vocabulary
- An outbox with idempotency keys, body hashes, and reconciliation markers
- Marker-based reconciliation so a repeated run never double-posts

**Dashboard preview** (`el_hidratador/dashboard.py`)

- Loopback-only, HTTP-only, no-redirect client with an 8 MiB cap and a 10 s
  timeout

**Ticket storage** (`el_hidratador/tickets.py`)

- Portable markdown tickets with front matter, an index, and per-task evidence
  files
- Atomic writes

**Command line interface** (`el_hidratador/cli.py`)

- Twenty-three JSON-first commands
- Exit codes: `0` success, `2` refused operation, `3` adapter failure

**Documentation and repository**

- Full documentation set under `docs/`, a runnable walkthrough under
  `examples/`, and a pinned MkDocs configuration
- Continuous integration across Linux and macOS on Python 3.11 through 3.14
- CodeQL, OpenSSF Scorecard, dependency review, `pip-audit`, and Bandit
- Issue forms, a pull request template, `CODEOWNERS`, and a labeler
- Discussion and wiki enablement, release automation, and a published
  documentation site

[Unreleased]: https://github.com/hamanakam1/el-hidratador/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hamanakam1/el-hidratador/releases/tag/v0.1.0
