# El Hidratador — Engineering Handoff & Architecture Blueprint

**Version:** 1.0  
**Author:** Michael Hamanaka  
**License:** MIT  

---

## System Role

### The Context Expansion and Execution Staging Engine

**Pipeline Position:** Upstream from Taskrivet; Downstream from the Ticket Board.

---

## Objective

El Hidratador transforms a "dry" semantic work package from the Ticket Board into a fully
"hydrated" execution state. It bridges the gap between human-approved intent and deterministic
machine action by:

1. Retrieving required codebase history
2. Expanding the context window for local LLM inference
3. Scaffolding the precise containerized workspace before Taskrivet executes

---

## Core Mechanisms

### 1. Context Injection & Token Expansion

A standard ticket lacks the explicit state needed for autonomous execution. El Hidratador
enriches it by:

- **Cloning the target Git branch** and establishing the working directory
- **Querying the local EdgeRecord ledger** to append immutable historical context, past
  decisions, and relevant post-mortems
- **Expanding a lightweight 50-word semantic ticket** into a densely packed,
  multi-thousand-token prompt specifically formatted for Qwen

### 2. The Execution DAG (Directed Acyclic Graph)

Before handing anything to the execution layer, the system computes the exact sequence of events:

- **Parses the hydrated context** to map out dependent vs. parallel tasks
- **Generates a strict execution manifest** detailing:
  - Which files need modification
  - Which tests must be written
  - The chronological order of operations

### 3. Environment Provisioning

Taskrivet lands in a fully prepped, isolated sandbox. El Hidratador manages this physical staging:

- **Spins up Docker containers** based on project requirements
- **Mounts appropriate local volumes** including code repositories and immutable logging
  directories
- **Locks environment boundaries** so Taskrivet cannot modify files outside the immediate scope
  of the active DAG node

---

## Hardware Routing & Compute Dispatch

Given the local-first architecture, compute resources must be allocated efficiently:

| Workload Type | Target Hardware | Rationale |
|---------------|-----------------|-----------|
| **Heavy Cognitive Loads** | Apple Silicon M3 Max | Context expansion, deep codebase scanning, complex DAG generation; utilizes unified memory for Ollama inference |
| **Lightweight Staging** | Micro-nodes & Raspberry Pi 5 clusters | Parallelized background scripts, sandbox provisioning, basic repository cloning |

---

## Handoff to Taskrivet

Once the environment is fully provisioned and the DAG is mapped, El Hidratador passes the
baton. The payload sent to Taskrivet consists of:

| Component | Description |
|-----------|-------------|
| **Active Sandbox** | A ready-to-build Docker container with all dependencies locked |
| **Manifest** | The first actionable node of the DAG |
| **Hydrated Prompt** | The exact command, complete with EdgeRecord history and architectural guidelines, requiring zero further logical deduction |

---

## Failure & Rollback

If Taskrivet triggers an execution failure:

1. **State rolls back to El Hidratador**
2. **Error logged immutably** in the ledger
3. **Two paths:**
   - Regenerate the prompt context with error context
   - Halt the DAG for operator intervention

---

## Ticket Schema (Markdown Front-Matter + Body)

```markdown
---
id: "M-397001"
title: "Implement JWT-based authentication for API endpoints"
status: "IN_PROGRESS"
priority: 1  # P0=Critical | P1=High | P2=Medium | P3=Low
kind: "code"  # code | fix | closure | planning | product
scope: ["repo/api", "repo/auth"]  # resource keys for conflict detection
token_budget: 8000
tags: ["security", "auth", "api"]
depends_on: ["M-397001", "M-397006"]  # prerequisite tickets
blocks: ["M-397015"]  # tickets blocked by this one
owner: "terminal-1"
seed_key: "auth-jwt-v1"
created_at: "2026-10-21T14:30:00Z"
updated_at: "2026-10-21T15:45:00Z"
---

## Description
Implement proper JWT-based authentication for API endpoints with token issuance, refresh rotation, revocation, and introspection (RFC 7662).

## Tasks
- [x] Design JWT token structure and claims
- [x] Implement token issuance endpoint
- [x] Add token validation middleware
- [x] Implement refresh token rotation
- [x] Add token revocation/blacklist mechanism
- [ ] Integrate with existing session management
- [ ] Add JWT configuration options (expiry, algorithm, issuer)

## Dependencies
- M-397001 (completed)
- M-397006 (middleware)

## Files Created
- `auth/jwt.py` - JWT authentication utilities
- `auth/middleware.py` - JWT validation middleware
- `auth/routes.py` - Route handlers (login, refresh, revoke, introspect, logout)

## Evidence Log
| Timestamp | Actor | Action | Evidence |
|-----------|-------|--------|----------|
| 2026-10-21T14:30:00Z | terminal-1 | started | Created JWT module with HS256/RS256 support |
| 2026-10-21T15:00:00Z | terminal-1 | checkpoint | Implemented token issuance + refresh rotation |
| 2026-10-21T15:30:00Z | terminal-1 | finished | All endpoints functional, tests pass |

## Acceptance Criteria
- [ ] POST /api/auth/login returns access+refresh token pair
- [ ] POST /api/auth/refresh rotates access token
- [ ] POST /api/auth/revoke invalidates token
- [ ] POST /api/auth/introspect returns RFC 7662 response
- [ ] All endpoints return proper RFC 7807 error responses
- [ ] 100% unit test coverage on auth module

```

---

## Ticket Lifecycle Stations

```text
INBOX → READY → IN_PROGRESS ↔ BLOCKED → REVIEW → ACCEPTED → DONE
                    ↑           ↓
                    └───────────┘ (retry)
```

| Station | Entry Criteria | Exit Criteria | Gate |
|---------|---------------|---------------|------|
| **INBOX** | Ticket created | Triaged by owner | — |
| **READY** | Scope defined, token_budget set, dependencies met | Owner assigned | — |
| **IN_PROGRESS** | `start()` called, lease acquired | `checkpoint()` with evidence or `fail()` | Lease expiry auto-blocks |
| **BLOCKED** | Lease expired, budget exhausted, or `fail()` called | `decide(retry)` or reconciliation | Lease renewal |
| **REVIEW** | `finish()` called with evidence | `decide(accept)` or `decide(retry)` | Human/operator gate |
| **ACCEPTED** | `decide(accept)` | Auto-transition to DONE | — |
| **DONE** | Immutable | — | — |

---

## Status Values

Statuses are stored and emitted in uppercase. Lowercase input is accepted and
normalized.

| Status | Meaning | Next Valid Transitions |
|--------|---------|------------------------|
| `INBOX` | Created, not triaged | → `READY` |
| `READY` | Triaged, ready for work | → `IN_PROGRESS`, → `CANCELLED` |
| `IN_PROGRESS` | Active lease, work happening | → `BLOCKED`, → `REVIEW` |
| `BLOCKED` | Lease expired, budget exhausted, no progress, or failed | → `READY` (retry), → `CANCELLED` |
| `REVIEW` | Work finished, awaiting acceptance | → `ACCEPTED`/`DONE`, → `READY` (retry), → `CANCELLED` |
| `ACCEPTED` | Accepted by operator | → `DONE` (immediate) |
| `DONE` | Immutable | — |
| `CANCELLED` | Explicitly cancelled | — |

---

## Evidence Requirements

| Station | Required Evidence |
|---------|-------------------|
| `checkpoint` | `summary`, `evidence` (diff/link), `next_step`, cumulative `tokens` |
| `finish` | Cumulative `evidence` (all checkpoints), final `summary` |
| `fail` | `category` (lease_expired\|budget\|tool\|dependency\|no_progress), `summary` |
| `decide(accept)` | Operator review of all evidence |
| `decide(retry)` | `reason` for retry (what changed) |

---

## Resource Scope & Conflict Detection

```yaml
scope: ["repo/api", "repo/auth"]  # Resource keys
```

- Scopes are **resource keys** (not descriptions)
- Two tickets with overlapping scopes **cannot** be `in_progress` simultaneously
- `blocked` tickets retain reservations until `reconcile()` or `decide(retry)`
- `decide(retry)` releases old reservation before new `start()`

---

## Token Budget Model

```yaml
token_budget: 8000  # cumulative across all attempts
```

- `tokens` in `checkpoint()` is **cumulative session count** (never decreases)
- Budget exhausted → `blocked` (cannot `start` new session)
- `decide(retry)` preserves cumulative tokens across retries
- Three consecutive checkpoints with **identical evidence hash** → `blocked` (no_progress)

---

## Failure Model

```yaml
category: lease_expired | budget | tool | dependency | no_progress
fingerprint: sha256(category:summary)[:16]  # stable grouping
```

- Failures auto-group by fingerprint
- Three consecutive identical evidence → `no_progress` failure
- Budget exhausted → `budget` failure (cannot `start` until `retry`)
- Lease expiry → `lease_expired` (preserves scope reservation)

---

## Acceptance Protocol

```text
finish() → status=review
    ↓
operator reviews evidence
    ↓
decide(accept) → status=accepted → DONE
decide(retry)  → status=ready    → IN_PROGRESS (new session)
decide(cancel) → status=cancelled
```

**Never** bypass the acceptance gate. `finish()` only creates `review`; only
`decide(accept)` creates `done`.

---

## CLI Interface (JSON-First)

Every command prints exactly one JSON object. Exit codes: `0` success, `2`
refused operation, `3` adapter failure.

```bash
# Lifecycle
hidratador task-add M-397001 --objective "..." --acceptance "..." --scope repo/api --budget 8000
hidratador task-show M-397001
hidratador task-list --status BLOCKED
hidratador triage M-397001
hidratador start M-397001 --owner terminal-1 --lease 900
hidratador checkpoint <sid> --summary "..." --evidence "..." --next "..." --tokens 1200
hidratador fail <sid> --category tool --summary "Compiler missing"
hidratador finish <sid> --evidence "All endpoints tested; diff abc123"
hidratador decide M-397001 accept --reason "Reviewed diff and tests"

# Context & packets
hidratador context-add M-397001 --file ./README.md --source-label "repo readme" --priority 10
hidratador pack M-397001 --max-bytes 12000 --packet-only
hidratador expand M-397001 --max-bytes 12000 --prompt

# Staging & routing
hidratador dag M-397001
hidratador handoff M-397001 --max-bytes 12000 --workdir /absolute/path
hidratador profile-add local-coder --kind code --context-limit 16000 --cost zero_incremental
hidratador route M-397001 --required-context 8000

# Observation & reporting
hidratador status
hidratador reconcile
hidratador events --after 0
hidratador export --dir .hidratador

# Adapters (opt-in)
hidratador github-poll --repo owner/repo            # dry run; add --apply to persist
hidratador github-publish --repo owner/repo --issue 123 --key summary --body "..."
hidratador dashboard-preview --url http://127.0.0.1:8080 --status planned --offset 0
```

---

## GitHub Sync Contract

### Observations (Read-Only)

```sql
observations(repo, kind, identity, revision, observed, summary, action, url)
```

- `kind`: `issues`, `comments`, `pulls`, `review_comments`, `releases`, `runs`, `commits`, `events`
- `action`: `investigate_failed_check`, `review_code_change`, `reconcile_ticket_change`,
  `review_external_feedback`, `verify_release_artifacts`, `inspect_repository_activity`

### Outbox (Write Path)

```sql
outbox(repo, issue, key, body_hash, state, url)
```

- `key`: Idempotency key (max 100 chars)
- `body_hash`: SHA-256 of body
- `marker`: `<!-- hidratador:{key}:{digest} -->` appended to body
- Reconciliation: reads comments, matches marker + actor, never blindly resends

---

## Ticket File Storage

```text
.hidratador/
├── tickets/
│   ├── M-397001.md
│   ├── M-397002.md
│   └── ...
├── index.json          # { "M-397001": { "title": "...", "status": "..." }, ... }
└── evidence/
    └── M-397001/
        ├── checkpoint-1.json
        ├── checkpoint-2.json
        └── finish.json
```

---

## Testing Requirements

| Layer | Coverage Target | Tools |
|-------|----------------|-------|
| Unit (pure functions) | 100% of public functions | `unittest` (CI also runs `pytest`) |
| Ledger lifecycle | 100% of documented transitions and refusals | `unittest` |
| Concurrency and leases | Explicit: expiry, scope reservation, duplicate claim | `unittest` |
| Budget boundaries | Explicit: cumulative across attempts, stagnation, exhaustion | `unittest` |
| Adapters | Failure paths with no network and no Docker daemon | `unittest` with stubbed boundaries |
| Property-based | Reserved for the byte-budget and ordering invariants | `hypothesis` (optional) |

The suite must pass on Linux and macOS, on Python 3.11 through 3.14, with no
network access and no Docker daemon present.

---

## Security Boundaries

| Boundary | Rule |
|----------|------|
| **Core** | No network, no shell exec, no telemetry, stdlib-only |
| **Adapters** | Declare supported versions, permission model, cancellation semantics |
| **Adapters** | No credentials in fixtures, synthetic only |
| **Dashboard** | Local HTTP only, no redirects, 8 MiB limit, 10s timeout |
| **GitHub** | `gh` CLI only, no token in code, 30s timeout |
| **Secrets** | Never in repo, injected via env/CSI at deploy |

---

## File Templates

### New Ticket Template

```markdown
---
id: "M-XXXXXX"
title: ""
status: "INBOX"
priority: 2
kind: "code"
scope: []
token_budget: 8000
tags: []
depends_on: []
blocks: []
owner: ""
seed_key: ""
created_at: "2026-10-21T00:00:00Z"
updated_at: "2026-10-21T00:00:00Z"
---

## Description

## Tasks
- [ ] 

## Dependencies
- 

## Files Created

## Acceptance Criteria
- [ ] 

```

### Checkpoint Evidence File

```json
{
  "session_id": "abc123",
  "sequence": 1,
  "summary": "Implemented token issuance endpoint",
  "evidence": "Diff abc123; POST /api/auth/login returns access+refresh pair",
  "next_step": "Implement refresh rotation",
  "tokens": 1200,
  "created_at": "2026-10-21T15:00:00Z",
  "evidence_hash": "sha256:..."
}
```

---

## Governance

- **Standard evolves** via tickets against this repo
- **Breaking changes** require `M-XXXXXX` migration ticket
- **Schema version** in `meta` table
- **Migrations** are additive + idempotent

---

## Implementation Status

This blueprint is implemented in `el_hidratador/`:

| Blueprint element | Module | Status |
|-------------------|--------|--------|
| Ticket ledger, lifecycle, leases, budgets, failures, events | `core.py` | Implemented |
| Context injection and token expansion | `context_expander.py` | Implemented |
| Execution DAG and manifest | `dag.py` | Implemented |
| Environment provisioning (sandbox specification) | `sandbox.py` | Implemented (specification first, Docker adapter opt-in) |
| Hardware routing and compute dispatch | `hardware_router.py` | Implemented (eligibility only) |
| Durable GitHub observations and outbox | `github_sync.py` | Implemented (`gh` CLI adapter) |
| Local dashboard preview | `dashboard.py` | Implemented (loopback only) |
| Ticket file storage | `tickets.py` | Implemented |
| JSON-first CLI | `cli.py` | Implemented |

Not yet implemented, and deliberately so:

- Automatic DAG inference from source code. The current DAG comes from ticket
  structure; code-derived graph extraction is a roadmap item.
- Provider-side verification of compute profiles. Every profile is an operator
  declaration until outcome evidence exists.
- Automatic acceptance. Nothing reaches `DONE` without `decide(accept)`.

---

## License

MIT License — see [LICENSE](LICENSE)
