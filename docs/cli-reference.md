# CLI reference

The CLI is JSON-first. **Every command prints exactly one JSON object on stdout** — nothing else is
written there, so the output can be piped straight into `jq` or parsed by a script without stripping
prose. Diagnostics go to the JSON object, not to stderr prose.

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | The command succeeded |
| `2` | A refused operation: validation failure, conflict, exhausted budget, expired lease, missing file, or an argparse usage error |
| `3` | An adapter failure: the `gh` CLI, the dashboard, or Docker refused or was unreachable |
| `130` | Interrupted at the keyboard |

Every successful payload carries `"ok": true` and `"command": "<name>"`. Every refusal carries
`"ok": false`, `"error": "<message>"`, and `"kind": "<ErrorTypeName>"` — for adapter failures
`"kind"` is the literal string `"adapter"`.

---

## Global flags

| Flag | Default | Effect |
|------|---------|--------|
| `--db PATH` | `$HIDRATADOR_DB`, else `~/.el-hidratador/ledger.sqlite` | Path to the ledger database. The directory is created if needed; the database file is chmod `0600`. |
| `--compact` | off | Print the JSON on a single line instead of indented. Keys are sorted in both modes. |
| `--version` | — | Print `hidratador <version>` and exit. |

Global flags come **before** the subcommand:

```bash
hidratador --compact --db /tmp/demo.sqlite status
```

The `--db` flag is accepted by every command, but `github-poll`, `github-publish`, and
`dashboard-preview` do not read from the ledger: they use their own stores (the GitHub sync
database, and the local dashboard respectively).

---

## Ledger and audit

### `init`

Create (or open) the ledger database and apply any pending migrations.

```bash
hidratador --db /tmp/demo.sqlite init
```

```json
{
  "database": "/tmp/demo.sqlite",
  "initialized": true,
  "schema_version": 3
}
```

### `status`

A snapshot of the whole ledger: all tasks, all sessions, a failure summary grouped by fingerprint,
and the metrics block.

```bash
hidratador status
```

```json
{
  "command": "status",
  "database": "/tmp/demo.sqlite",
  "failures": [],
  "metrics": {
    "accepted": 1,
    "measured_cash_cost": null,
    "measured_token_savings": null,
    "note": "Reported tokens are declared by workers, not metered by a provider.",
    "reported_tokens": 1500
  },
  "ok": true,
  "schema_version": 3,
  "sessions": [
    {
      "created": 1792655698.762271,
      "error": "",
      "id": "b2f10e7990064f3cb1e8e55a0639cf70",
      "lease_until": 1792656603.3979468,
      "owner": "terminal-1",
      "progress": "630be5cf2e5a097b90c451366e3ebfdb616e0b5441ee311ffb1569c2c3b26fed",
      "stagnant": 0,
      "status": "finished",
      "stop_reason": "",
      "task_id": "M-1001",
      "tokens": 1500,
      "warning": ""
    }
  ],
  "tasks": [
    {
      "id": "M-1001",
      "status": "DONE",
      "title": "Add request id echo endpoint"
    }
  ],
  "tasks_by_status": {
    "DONE": 1
  }
}
```

`measured_cash_cost` and `measured_token_savings` are `null` on purpose: this package does not meter
providers and cannot report cost.

### `reconcile`

Expire stale leases and report which tasks were affected. Expiry moves the session to `expired`,
moves the task to `BLOCKED`, and records a `lease_expired` failure.

```bash
hidratador reconcile
```

```json
{
  "command": "reconcile",
  "expired_count": 1,
  "expired_tasks": ["M-2001"],
  "ok": true
}
```

### `events`

The append-only audit log.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `--after N` | int | `0` | Return only events with `seq > N`. Use it to page through the log. |

```bash
hidratador events --after 8
```

```json
{
  "command": "events",
  "count": 0,
  "events": [],
  "ok": true
}
```

Each event is `{seq, type, task_id, data, created, created_iso}`. Event types: `task.created`,
`task.updated`, `task.triaged`, `session.started`, `session.checkpoint`, `session.finished`,
`failure.recorded`, `context.attached`, `profile.declared`, `handoff.recorded`, `operator.accept`,
`operator.retry`, `operator.cancel`, `task.done`.

---

## Tasks

### `task-add`

Create a task in `INBOX`.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. Becomes the ledger primary key. |
| `--objective` | str | required | What the work must accomplish. Nonempty. |
| `--acceptance` | str | required | How completion is judged. Nonempty. |
| `--title` | str | `""` | Short title. Defaults to the first 120 characters of the objective. |
| `--kind` | str | `code` | One of `code`, `fix`, `closure`, `planning`, `product`. |
| `--scope` | str | repeatable | A resource key. Repeat the flag for more than one. Defaults to the task id when omitted. |
| `--budget` | int | `8000` | Cumulative token budget across all attempts. Must be positive. |
| `--tags` | str | `""` | Comma-separated tags. |
| `--depends-on` | str | `""` | Comma-separated prerequisite task ids. |
| `--blocks` | str | `""` | Comma-separated ids of tasks this one blocks. |
| `--owner` | str | `""` | Owning terminal or agent. |
| `--seed-key` | str | `""` | Idempotency key. Repeating it returns the original task instead of creating a duplicate. |
| `--priority` | int | `2` | `1` (P0) through `3` (P3). |
| `--description` | str | `""` | Markdown body. `dag` parses this for the task list and file sections. |

```bash
hidratador task-add M-1001 \
  --title "Add request id echo endpoint" \
  --objective "Expose GET /healthz that returns the request id assigned by the edge proxy." \
  --acceptance "GET /healthz returns 200 with a request id header; unit test passes." \
  --scope repo/api --scope terminal-1 \
  --budget 4000 --tags api,health --priority 2 --owner terminal-1
```

```json
{
  "command": "task-add",
  "created": true,
  "idempotent": false,
  "ok": true,
  "task_id": "M-1001"
}
```

Re-running with the same `--seed-key` returns `"created": false, "idempotent": true`.

### `task-show`

One task as a dictionary.

```bash
hidratador task-show M-1001
```

Returns the ticket fields: `id`, `title`, `objective`, `acceptance`, `kind`, `scope`, `status`,
`priority`, `token_budget`, `tags`, `depends_on`, `blocks`, `owner`, `seed_key`, `description`,
`acceptance_criteria`, `created_at`, `updated_at`, `created_at_iso`, `updated_at_iso`, plus
`"command"` and `"ok"`.

### `task-list`

List tasks, optionally filtered by status.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `--status` | str | none | One of `INBOX`, `READY`, `IN_PROGRESS`, `BLOCKED`, `REVIEW`, `ACCEPTED`, `DONE`, `CANCELLED`. Case-insensitive on input. |

```bash
hidratador task-list --status DONE
```

```json
{
  "command": "task-list",
  "count": 1,
  "ok": true,
  "tasks": [
    {
      "id": "M-1001",
      "status": "DONE",
      "title": "Add request id echo endpoint"
    }
  ]
}
```

### `triage`

Move a task from `INBOX` to `READY`. Refuses if the task is not in `INBOX` or has no scope.

```bash
hidratador triage M-1001
```

Returns the full ticket dictionary with `"status": "READY"`.

---

## Sessions and the lifecycle

### `start`

Acquire an execution lease. Moves the task to `IN_PROGRESS`.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `--owner` | str | required | Owning terminal or agent. |
| `--lease` | int | `900` | Lease duration in seconds. Must be positive. |

```bash
hidratador start M-1001 --owner terminal-1 --lease 900
```

```json
{
  "command": "start",
  "lease_until": 1792656201.623849,
  "lease_until_iso": "2026-10-22T08:03:21.623Z",
  "ok": true,
  "session_id": "1c1709f4c78a46f688ee3cf248ac2427",
  "task_id": "M-1001",
  "token_budget": 4000,
  "tokens_used": 0
}
```

Refuses with `Conflict` when the task is not `READY`/`INBOX`, when another live task holds an
overlapping scope key, or when the task already has an active session. Refuses with
`BudgetExceeded` when cumulative tokens across attempts have reached the budget.

### `checkpoint`

Record progress. All four content flags are required.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `session` (positional) | str | — | Session id from `start`. |
| `--summary` | str | required | What was done. Nonempty. |
| `--evidence` | str | required | The proof: a diff, a log line, a test result. Nonempty. |
| `--next` | str | required | The next concrete step. Nonempty. |
| `--tokens` | int | required | Cumulative token count for the session. Nonnegative and never decreasing. |
| `--lease` | int | `900` | New lease duration in seconds, measured from now. |

```bash
hidratador checkpoint 1c1709f4c78a46f688ee3cf248ac2427 \
  --summary "Route table registered" \
  --evidence "diff 4f1c: router.py adds /healthz" \
  --next "Add request id header" \
  --tokens 900
```

```json
{
  "command": "checkpoint",
  "evidence_hash": "a76892a0397f3a6abc3abcc0621b2734ee0699168d93951a04c4853d2e4e9a0f",
  "ok": true,
  "session_id": "1c1709f4c78a46f688ee3cf248ac2427",
  "stagnant": 0,
  "status": "active",
  "tokens": 900
}
```

`status` becomes `"blocked"` when the cumulative budget is reached or when the evidence hash repeats
three times in a row. `stagnant` counts consecutive identical evidence hashes.

### `fail`

Record an explicit failure and block the task.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `session` (positional) | str | — | Session id. |
| `--category` | str | required | One of `lease_expired`, `budget`, `tool`, `dependency`, `no_progress`. |
| `--summary` | str | required | What went wrong. Nonempty. |

```bash
hidratador fail 1c1709f4c78a46f688ee3cf248ac2427 \
  --category dependency \
  --summary "Upstream schema missing column request_id"
```

```json
{
  "category": "dependency",
  "command": "fail",
  "fingerprint": "30b9d5144fe36d3e",
  "ok": true,
  "status": "BLOCKED",
  "task_id": "M-1001"
}
```

### `finish`

Request review. Moves the task to `REVIEW`. Requires at least one checkpoint on the session.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `session` (positional) | str | — | Session id. |
| `--evidence` | str | required | Cumulative evidence for the whole attempt. Nonempty. |

```bash
hidratador finish 1c1709f4c78a46f688ee3cf248ac2427 \
  --evidence "GET /healthz returns 200 with X-Request-Id; unit test green"
```

```json
{
  "command": "finish",
  "ok": true,
  "status": "REVIEW",
  "task_id": "M-1001"
}
```

`finish` never produces `DONE`. Only `decide accept` does.

### `decide`

Record an operator decision.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `decision` (positional) | choice | — | `accept`, `retry`, or `cancel`. |
| `--reason` | str | required | Why. Nonempty. |

| Decision | Allowed from | Result |
|----------|--------------|--------|
| `accept` | `REVIEW` | `ACCEPTED`, then `DONE` |
| `retry` | `BLOCKED`, `REVIEW` | `READY` (cumulative tokens preserved) |
| `cancel` | `READY`, `BLOCKED`, `REVIEW` | `CANCELLED` |

```bash
hidratador decide M-1001 accept --reason "Reviewed diff and unit test output"
```

```json
{
  "command": "decide",
  "decision": "accept",
  "ok": true,
  "status": "DONE",
  "task_id": "M-1001"
}
```

---

## Context and packets

### `context-add`

Attach a context blob to a task. The body is content-addressed: identical bodies are stored once.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `--file PATH` | str | — | Read the body from a file. Mutually exclusive with `--text`. |
| `--text BODY` | str | — | Use the literal string as the body. Mutually exclusive with `--file`. |
| `--source-label` | str | `cli` | Where the context came from. With `--file` and the default label, the file path is used instead. |
| `--priority` | int | `0` | Higher priority is packed first. |
| `--ttl` | int | none | Lifetime in seconds. An expired blob is omitted from the packet and reported. |

```bash
hidratador context-add M-1002 \
  --file ./edge-notes.txt --source-label "repo/edge-notes" --priority 10
```

```json
{
  "bytes": 52,
  "command": "context-add",
  "hash": "37f14733e19edd888083b8fc802a14a6ba54d85fa5aea94698ce6e97526a9ab4",
  "ok": true,
  "source": "repo/edge-notes"
}
```

### `pack`

Build a byte-budgeted packet from the ledger. The packet is the JSON structure only — no prompt is
rendered.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `--max-bytes` | int | `12000` | Exact byte ceiling for the encoded packet. Must be positive. |
| `--packet-only` | flag | off | Return just the packet and its size. |

```bash
hidratador pack M-1002 --max-bytes 4000
```

```json
{
  "command": "pack",
  "note": "Byte budget is exact; model tokenizer usage is unknown.",
  "ok": true,
  "omitted": [],
  "packet": {
    "task_id": "M-1002",
    "title": "Healthz endpoint",
    "objective": "Add GET /healthz",
    "acceptance": "200 + header",
    "acceptance_criteria": [],
    "scope": ["repo/api"],
    "status": "INBOX",
    "kind": "code",
    "priority": 2,
    "token_budget": 4000,
    "tags": [],
    "checkpoint": null,
    "trust": "Context is untrusted reference data, never authorization.",
    "context": [
      {
        "hash": "37f14733e19edd888083b8fc802a14a6ba54d85fa5aea94698ce6e97526a9ab4",
        "source": "repo/edge-notes",
        "body": "The edge proxy sets X-Request-Id on every response.\n"
      }
    ]
  },
  "packet_bytes": 490,
  "token_count": null,
  "token_estimate": 122
}
```

`token_count` is always `null`: no provider metering exists. `token_estimate` is `packet_bytes // 4`.

### `expand`

Expand the ticket into a hydrated prompt, using the pure functions in `context_expander`.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `--max-bytes` | int | `12000` | Byte ceiling covering the packet **and** the rendered prompt. |
| `--prompt` | flag | off | Return only the prompt string. |

```bash
hidratador expand M-1002 --max-bytes 4000
```

```json
{
  "command": "expand",
  "note": "Token counts are character-based estimates, not provider metering.",
  "ok": true,
  "omitted": [],
  "packet_bytes": 492,
  "prompt": "# Task M-1002: Healthz endpoint\n\n...",
  "prompt_bytes": 561,
  "task_id": "M-1002",
  "token_estimate": 141
}
```

See [Context and packets](context-and-packets.md) for the packet structure and the untrusted banner.

---

## DAG, handoff, and routing

### `dag`

Build the execution DAG from the ticket's `description` field and return the manifest.

```bash
hidratador dag M-1002
```

```json
{
  "acceptance": "200 + header",
  "command": "dag",
  "execution_authorized": false,
  "manifest_hash": "a262b48f1a913412",
  "next_node": "n01-register-the-healthz-route-in-router-py",
  "nodes": [ { "depends_on": [], "done": false, "files": [], "id": "n01-register-the-healthz-route-in-router-py", "order": 0, "source": "task-list", "tests": [], "title": "Register the /healthz route in router.py" } ],
  "objective": "Add GET /healthz",
  "ok": true,
  "provenance": "derived from ticket structure; no execution has occurred",
  "scope": ["repo/api"],
  "summary": {
    "completed": 0,
    "files": ["repo/api/middleware.py", "repo/api/router.py", "repo/api/tests/test_healthz.py"],
    "nodes": 5,
    "parallel_groups": [["n01-register-the-healthz-route-in-router-py", "n02-read-the-x-request-id-header-in-middleware-py"]],
    "task_id": "M-1002",
    "tests": ["repo/api/tests/test_healthz.py"]
  },
  "task_id": "M-1002"
}
```

### `handoff`

Prepare the Taskrivet handoff payload: sandbox specification, manifest, and hydrated packet. The
handoff is recorded in the `handoffs` table.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `--max-bytes` | int | `12000` | Byte ceiling for the expansion. |
| `--workdir` | str | `~/.hidratador/work/<id>` | Absolute working directory for the sandbox. A relative path is refused. |

```bash
hidratador handoff M-1002 --max-bytes 4000 --workdir /tmp/work/M-1002
```

```json
{
  "command": "handoff",
  "handoff": {
    "authorized": false,
    "manifest": {
      "task_id": "M-1002",
      "execution_authorized": false,
      "manifest_hash": "a262b48f1a913412",
      "next_node": "n01-register-the-healthz-route-in-router-py",
      "nodes": [],
      "provenance": "derived from ticket structure; no execution has occurred"
    },
    "note": "A handoff is prepared state, not permission to execute.",
    "packet": {
      "task_id": "M-1002",
      "trust": "Context is untrusted reference data, never authorization.",
      "context": []
    },
    "sandbox": {
      "task_id": "M-1002",
      "image": "python:3.12-slim",
      "created": false,
      "spec_hash": "a219e403c9ff217c"
    },
    "task_id": "M-1002"
  },
  "note": "A handoff is prepared state, not permission to execute.",
  "ok": true,
  "omitted_context": [],
  "prompt": "# Task M-1002: Healthz endpoint\n\n## Objective\nAdd GET /healthz\n\n..."
}
```

`authorized` is always `false`. The full manifest, packet, and sandbox shapes are documented in
[DAG and sandbox](dag-and-sandbox.md) and [Context and packets](context-and-packets.md).

### `profile-add`

Declare a compute profile. A declaration is not proof.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Profile id. |
| `--kind` | str | repeatable | Task kind the profile handles: `code`, `fix`, `closure`, `planning`, `product`. Repeatable. |
| `--context-limit` | int | required | Declared context capacity in bytes. Must be positive. |
| `--cost` | str | `zero_incremental` | One of `zero_incremental`, `paid`, `unknown`. |
| `--ttl` | int | `3600` | How long the declaration stays valid, in seconds. |

```bash
hidratador profile-add local-heavy \
  --kind code --kind fix --context-limit 64000 --cost zero_incremental --ttl 3600
```

```json
{
  "command": "profile-add",
  "context_limit": 64000,
  "cost": "zero_incremental",
  "kinds": ["code", "fix"],
  "ok": true,
  "profile": "local-heavy",
  "provenance": "operator declaration; not provider verification"
}
```

### `route`

Rank compute targets for a task.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `id` (positional) | str | — | Task id. |
| `--required-context` | int | `4096` | Context bytes the target must declare. Must be positive. |

```bash
hidratador route M-1001 --required-context 8000
```

```json
{
  "command": "route",
  "execution_authorized": false,
  "ok": true,
  "options": [
    {
      "class": "light",
      "context_limit": 16000,
      "cost": "zero_incremental",
      "eligible": true,
      "provenance": "local declaration; no provider telemetry",
      "quality_estimate": null,
      "reasons": [],
      "target": "local-light"
    }
  ],
  "plan": {
    "dry_run": true,
    "execution_authorized": false,
    "note": "Dispatch requires an operator decision; the router never starts work.",
    "options": [],
    "plan_hash": "aa457c1322058730",
    "provenance": "local declaration; no provider telemetry",
    "target": "local-light",
    "task_id": "M-1001"
  },
  "provenance": "local declaration; no provider telemetry",
  "recommendation": "local-light",
  "task_id": "M-1001"
}
```

`execution_authorized` is always `false` and `quality_estimate` is always `null`. `recommendation` is
the first eligible target, or `null` when no target is eligible. The `plan` block repeats the same
option list under `plan.options`, so the abbreviated array above is empty in this example only.

---

## Export

### `export`

Write every ticket in the ledger to a file-backed ticket store.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `--dir` | str | `.hidratador` | Root of the ticket tree. |

```bash
hidratador export --dir .hidratador
```

```json
{
  "command": "export",
  "index": ".hidratador/index.json",
  "ok": true,
  "root": ".hidratador",
  "written": ["M-1001.md", "M-1002.md"]
}
```

Layout produced:

```text
.hidratador/
├── tickets/
│   └── M-1001.md
├── index.json
└── evidence/
    └── M-1001/
        └── checkpoint-1.json
```

The evidence directory is populated by `TicketStore.write_evidence()`, not by the CLI.

---

## Adapters

These three commands are the only ones that touch anything outside the local machine. They read no
ledger data, so `--db` changes nothing about what they do — but the CLI still opens the ledger, so
the file at that path is created if it does not exist.

### `github-poll`

Observe a repository. Read-only with respect to GitHub.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `--repo` | str | required | Repository in `owner/name` form. |
| `--apply` | flag | off | Persist the observations. Without it, the observations are returned but not stored. |

```bash
hidratador github-poll --repo acme/api
```

```json
{
  "dry_run": true,
  "observations": [
    {
      "action": "reconcile_ticket_change",
      "identity": "#42",
      "kind": "issues",
      "observed": "OPEN",
      "revision": "2026-10-21T09:00:00Z",
      "summary": "Add request id echo endpoint",
      "url": "https://github.com/acme/api/issues/42"
    }
  ],
  "repo": "acme/api"
}
```

### `github-publish`

Queue an idempotent comment and publish pending outbox entries.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `--repo` | str | required | Repository in `owner/name` form. |
| `--issue` | int | required | Issue number. Must be positive. |
| `--key` | str | required | Idempotency key. At most 100 characters, no newlines, no `<!--`. |
| `--body` | str | required | Comment body. Must be nonempty. |
| `--apply` | flag | off | Publish. Without it, the result is `would_publish` and nothing is written. |

```bash
hidratador github-publish --repo acme/api --issue 42 \
  --key handoff-M-1001 --body "Handoff prepared for M-1001"
```

```json
{
  "command": "github-publish",
  "ok": true,
  "publish": {
    "dry_run": true,
    "repo": "acme/api",
    "results": [
      {
        "action": "would_publish",
        "issue": 42,
        "key": "handoff-M-1001",
        "note": "dry run; no comment was written"
      }
    ]
  },
  "queued": {
    "body_hash": "69bbb7e186fa54d9dc20bfc3f1441d687247f92923ce7c7e2314545bc47cb233",
    "created": true,
    "issue": 42,
    "key": "handoff-M-1001",
    "repo": "acme/api",
    "state": "pending"
  }
}
```

### `dashboard-preview`

Read a window from a local dashboard over loopback HTTP.

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `--url` | str | required | `http://` URL on `localhost`, `127.0.0.1`, or `::1`. Credentials in the URL are refused. |
| `--status` | str | `planned` | Status label recorded in the response. |
| `--offset` | int | `0` | First row to return. Must be nonnegative. |
| `--limit` | int | `50` | Maximum rows to return. Must be positive. |

```bash
hidratador dashboard-preview --url http://127.0.0.1:8080/api/tasks --status planned --offset 0 --limit 50
```

```json
{
  "command": "dashboard-preview",
  "content_type": "application/json",
  "http_status": 200,
  "items": [ "..." ],
  "limit": 50,
  "note": "Preview reflects a local operator surface; it is not a source of truth.",
  "offset": 0,
  "ok": true,
  "returned": 1,
  "status_filter": "planned",
  "total": 1,
  "url": "http://127.0.0.1:8080/api/tasks"
}
```

---

## Piping examples

```bash
# Count tasks by status
hidratador --compact status | jq '.tasks_by_status'

# List tasks waiting for an operator
hidratador --compact task-list --status REVIEW | jq '.tasks[].id'

# Read only events added since the last sequence you saw
hidratador --compact events --after 42 | jq '.events[].type'

# Fail the script when the ledger reports a refusal
hidratador --compact status >/dev/null || exit 1
```

---

## Related pages

- [Context and packets](context-and-packets.md) — packet structure and budgets
- [DAG and sandbox](dag-and-sandbox.md) — manifest and sandbox schema
- [GitHub sync](github-sync.md) — adapter internals
- [Failure playbook](failure-playbook.md) — recovery commands
- [Operations](operations.md) — environment variables and backups
