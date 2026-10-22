---
id: M-1001
title: Add request id echo endpoint
status: IN_PROGRESS
priority: 2
kind: code
scope: [repo/api, terminal-1]
token_budget: 4000
tags: [api, health]
depends_on: []
blocks: []
owner: terminal-1
seed_key: healthz-request-id-v1
created_at: "2026-10-22T07:54:58.478Z"
updated_at: "2026-10-22T07:55:03.757Z"
---

## Description

The edge proxy sets `X-Request-Id` on every response. The health endpoint reads that header and
returns it unchanged, so a caller can correlate a health check with the proxy logs.

## Tasks

- [x] Register the /healthz route in router.py
- [x] Read the X-Request-Id header in middleware.py
- [ ] Add a unit test for the health endpoint
- [ ] Write the operator runbook entry

## Dependencies

- M-1000 (edge proxy header contract, completed)

## Files Created

- `repo/api/router.py` - route table with the /healthz entry
- `repo/api/middleware.py` - request id middleware
- `repo/api/tests/test_healthz.py` - health endpoint test

## Evidence Log

| Timestamp | Actor | Action | Evidence |
|-----------|-------|--------|----------|
| 2026-10-22T07:54:58Z | terminal-1 | started | acquired lease on M-1001 |
| 2026-10-22T07:55:03Z | terminal-1 | checkpoint | diff 4f1c2d: router.py adds GET /healthz |
| 2026-10-22T07:55:03Z | terminal-1 | checkpoint | diff 8ab3e1: middleware reads X-Request-Id |

## Acceptance Criteria

- [ ] GET /healthz returns 200 with the X-Request-Id header
- [ ] A unit test covers the endpoint

---

## Appendix: how this file is read

The part above the `---` separator is the ticket as `TicketStore` writes it. The part below is
documentation about the format. When the ticket is stored in the ledger, only the front matter and
the body sections are kept; this appendix is commentary for readers of the repository.

### Front matter

`TicketStore.render_ticket()` emits exactly these keys, in this order:

| Key | Type | Meaning |
|-----|------|---------|
| `id` | string | Ticket id. Must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`. |
| `title` | string | Short title |
| `status` | string | Lifecycle station: `INBOX`, `READY`, `IN_PROGRESS`, `BLOCKED`, `REVIEW`, `ACCEPTED`, `DONE`, `CANCELLED` |
| `priority` | integer | `1` (P0) through `3` (P3) |
| `kind` | string | `code`, `fix`, `closure`, `planning`, or `product` |
| `scope` | list | Resource keys. Two live tasks cannot share one. |
| `token_budget` | integer | Cumulative token budget across all attempts |
| `tags` | list | Free-form labels |
| `depends_on` | list | Prerequisite ticket ids |
| `blocks` | list | Ticket ids this one blocks |
| `owner` | string | Owning terminal or agent |
| `seed_key` | string | Idempotency key for task creation |
| `created_at` | string | ISO-8601 UTC timestamp |
| `updated_at` | string | ISO-8601 UTC timestamp |

The front matter is written by `render_front_matter()`. Values containing `:`, `#`, `"`, `'`, a
newline, or leading and trailing whitespace are quoted and escaped. Lists are rendered inline as
`[a, b]`.

`parse_front_matter()` reads the same file back. It is a deliberately small parser: it reads the
first `---` block, splits each line on the first `:`, and treats a bracketed value as a
comma-separated list.

### The body

The body is what `build_dag()` parses. Only two sections have a defined syntax.

**`## Tasks`** — one checkbox per line:

```text
- [ ] Add a unit test for the health endpoint
- [x] Register the /healthz route in router.py

```

The bullet may be `-` or `*`. The box may be `[ ]`, `[x]`, or `[X]`. A ticked box marks the node
`done: true`.

A dependency clause may follow the text:

```text
- [ ] Write the unit test requires n03-add-a-unit-test-for-the-health-endpoint

```

The keywords are `depends on`, `requires`, and `after` (case-insensitive). Ids are alphanumeric with
`-` and `_`, separated by commas. The clause is removed from the node title.

**`## Files Created`** — one path per line, optionally with a note:

```text
- `repo/api/router.py` - route table with the /healthz entry
- repo/api/plain.py

```

The path may be backticked or bare. The note follows a dash, en dash, em dash, or colon. The heading
must be a level-2 heading: `### Files Created` does not open the section.

`## Tests` uses the same syntax and is preferred for test paths. When no `## Tests` section exists,
test paths fall back to the `Files Created` entries whose path contains `test`.

### Sections the parser ignores

`## Description`, `## Dependencies`, and `## Evidence Log` are read by humans and by review tools.
The DAG parser ignores them.

`## Dependencies` is not a machine-readable source of dependencies. Dependencies reach the graph
through the `depends_on` front-matter key and the inline task clauses.

### One behaviour worth knowing

`parse_tasks()` scans the **entire** body for checkboxes. The two `- [ ]` lines under
`## Acceptance Criteria` therefore become execution nodes as well, which is why the ticket above
produces six nodes rather than four:

| Node | Source |
|------|--------|
| `n01-register-the-healthz-route-in-router-py` | `## Tasks` |
| `n02-read-the-x-request-id-header-in-middleware-py` | `## Tasks` |
| `n03-add-a-unit-test-for-the-health-endpoint` | `## Tasks` |
| `n04-write-the-operator-runbook-entry` | `## Tasks` |
| `n05-get-healthz-returns-200-with-the-x-request-id-he` | `## Acceptance Criteria` |
| `n06-a-unit-test-covers-the-endpoint` | `## Acceptance Criteria` |

The file paths in `## Files Created` did not appear inside any node title, so all three were
attached to the last node, `n06-a-unit-test-covers-the-endpoint`. When a path *does* appear in a
node title — for example a task written as "Update `repo/api/router.py`" — it is attached to that
node instead.

### Loading the ticket into the ledger

The ledger stores the body as the ticket's `description` field. The CLI takes it as a single
argument:

```bash
hidratador task-add M-1001 \
  --title "Add request id echo endpoint" \
  --objective "Expose GET /healthz that returns the request id assigned by the edge proxy." \
  --acceptance "GET /healthz returns 200 with the X-Request-Id header; a unit test covers it." \
  --scope repo/api --scope terminal-1 \
  --budget 4000 --tags api,health --priority 2 --owner terminal-1 \
  --seed-key healthz-request-id-v1 \
  --description "$(awk '/^## Description$/{f=1;next} /^## Dependencies$/{f=0} f' ticket.md)"
```

The `awk` range above extracts the description section from this file; in practice the body is
whatever the ticket board produced.

To check what the parser sees:

```bash
hidratador --compact dag M-1001 | jq '{node_count: (.nodes | length), next_node}'
```

---

## Related pages

- [DAG and sandbox](../docs/dag-and-sandbox.md) — the full parsing grammar and the manifest schema
- [Context and packets](../docs/context-and-packets.md) — how the packet uses files and tests
- [Walkthrough](walkthrough.md) — the same ticket shape, end to end
