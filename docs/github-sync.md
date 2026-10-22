# GitHub sync

The GitHub adapter has two halves, kept strictly apart:

- **Observations** are read-only. El Hidratador watches a repository and records what it saw. It
  never mutates GitHub state while observing.
- **The outbox** is the write path. Every write carries an idempotency key, a body hash, and a
  marker comment. Before sending, the adapter reconciles against what is already on the issue, so a
  repeated run never double-posts.

The adapter shells out to the `gh` CLI. **No token is ever read, stored, or passed through this
module** — `gh` owns authentication. The adapter database is separate from the ledger and lives at
`$HIDRATADOR_GITHUB_DB`, defaulting to `~/.el-hidratador/github.sqlite`.

---

## The dry-run-first rule

Both write-capable operations default to a dry run.

| Operation | Library default | CLI flag to make it real |
|-----------|-----------------|---------------------------|
| `GitHubSync.poll(repo, dry_run=True)` | `dry_run=True` | `hidratador github-poll --repo owner/name --apply` |
| `GitHubSync.publish(repo, dry_run=True)` | `dry_run=True` | `hidratador github-publish ... --apply` |

A dry-run poll returns the observations it would have stored without storing them. A dry-run publish
returns `would_publish` for each pending entry without writing a comment.

Note that `enqueue()` is **not** a dry run and is not gated by `--apply`: the CLI always writes the
queued entry to the adapter database. That is a local write to the outbox, not a write to GitHub.

---

## Observations

### The table

```sql
observations(
    repo      TEXT NOT NULL,
    kind      TEXT NOT NULL,
    identity  TEXT NOT NULL,
    revision  TEXT NOT NULL DEFAULT '',
    observed  TEXT NOT NULL DEFAULT '',
    summary   TEXT NOT NULL DEFAULT '',
    action    TEXT NOT NULL DEFAULT '',
    url       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (repo, kind, identity)
)
```

The primary key makes observation recording idempotent: re-observing the same identity updates the
row in place.

| Column | Meaning |
|--------|---------|
| `repo` | `owner/name` |
| `kind` | One of the observation kinds below |
| `identity` | The thing observed, e.g. `#42` for an issue, a tag name for a release |
| `revision` | The version marker of the observation — `updatedAt`, `publishedAt`, or `createdAt` |
| `observed` | A short state value — `OPEN`, `CLOSED`, `draft`, `published`, or an author login |
| `summary` | A short human-readable summary |
| `action` | A recommended action from the vocabulary below, or empty |
| `url` | The URL of the observed object |

### Observation kinds

`OBSERVATION_KINDS` is a fixed tuple. `record_observation` refuses anything else with
`ValidationError: unknown observation kind: <kind>`.

| Kind | What it covers |
|------|----------------|
| `issues` | Issues in the repository |
| `comments` | Issue comments |
| `pulls` | Pull requests |
| `review_comments` | Pull request review comments |
| `releases` | Releases and drafts |
| `runs` | Workflow runs |
| `commits` | Commits |
| `events` | Repository activity events |

### The action vocabulary

`ACTIONS` is a fixed tuple. `record_observation` refuses anything else with
`ValidationError: unknown observation action: <action>`.

| Action | Meaning |
|--------|---------|
| `investigate_failed_check` | A check failed and needs investigation |
| `review_code_change` | A code change is waiting for review |
| `reconcile_ticket_change` | A ticket changed and the local copy is stale |
| `review_external_feedback` | Someone left feedback that needs a response |
| `verify_release_artifacts` | A release needs its artifacts verified |
| `inspect_repository_activity` | General repository activity needs inspection |

An observation may carry an empty action. Action means "this is what a human should consider", not
"this must be done".

### What `poll` actually reads

`poll()` issues four `gh` calls:

| Call | Fields | Observations produced |
|------|--------|-----------------------|
| `gh issue list --repo R --limit 100` | `number, title, state, url, labels, updatedAt` | One `issues` observation per issue |
| `gh issue view <n> --repo R --json comments` | `comments` | One `comments` observation per comment |
| `gh pr list --repo R --limit 100` | `number, title, state, url, updatedAt` | One `pulls` observation per pull request |
| `gh release list --repo R --limit 50` | `tagName, name, isDraft, publishedAt, url` | One `releases` observation per release |

Two rules are applied while collecting:

- An issue labelled `needs-triage` gets the action `reconcile_ticket_change`. Other issues get an
  empty action.
- Comment summaries are truncated to 280 characters. The full body is never stored.

### Reading observations back

```python
from el_hidratador.github_sync import GitHubSync

sync = GitHubSync()
try:
    everything = sync.observations()
    only_pulls = sync.observations(kind="pulls")
    for item in only_pulls:
        print(item["identity"], item["action"])
finally:
    sync.close()
```

`observations(repo=None, kind=None)` filters by either argument, or both, and orders by
`repo, kind, identity`.

---

## The outbox

### The table

```sql
outbox(
    repo      TEXT NOT NULL,
    issue     INTEGER NOT NULL,
    key       TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    body      TEXT NOT NULL DEFAULT '',
    state     TEXT NOT NULL DEFAULT 'pending',
    url       TEXT NOT NULL DEFAULT '',
    created   REAL NOT NULL,
    PRIMARY KEY (repo, issue, key)
)
```

The primary key is `(repo, issue, key)`. The same key on the same issue is one entry, forever.

| Column | Meaning |
|--------|---------|
| `repo` | `owner/name` |
| `issue` | Issue number |
| `key` | The idempotency key |
| `body_hash` | `sha256` of the body, hex |
| `body` | The comment body as supplied |
| `state` | `pending`, `reconciled`, or `published` |
| `url` | The comment URL, once known |
| `created` | Unix timestamp of enqueue |

### The idempotency key

`enqueue(repo, issue, key, body)` validates the key:

| Rule | Refusal |
|------|---------|
| Must be nonempty | `outbox key must be nonempty` |
| At most 100 characters | `outbox key must be 100 characters or fewer` |
| No newlines | `outbox key must not contain newlines or comment markers` |
| No `<!--` | `outbox key must not contain newlines or comment markers` |

A key names a *claim*, not a body. Reusing a key with a different body is refused:

```text
outbox key already used with a different body; use a new key or reconcile manually
```

Reusing a key with the same body is idempotent: the existing row is returned with
`"created": false`.

The repository is validated separately and must be in `owner/name` form — exactly one `/`, no empty
parts. Otherwise: `repo must be in owner/name form`.

### The body hash

```python
from el_hidratador.github_sync import body_hash

body_hash("Handoff prepared for M-1001")
# '69bbb7e186fa54d9dc20bfc3f1441d687247f92923ce7c7e2314545bc47cb233'
```

`sha256` of the body, hex-encoded, no truncation. It is computed over the body *before* the marker
is appended, and it is what the marker embeds.

### The marker

```python
from el_hidratador.github_sync import marker

marker("handoff-M-1001", "69bbb7e186fa54d9dc20bfc3f1441d687247f92923ce7c7e2314545bc47cb233")
```

```text
<!-- hidratador:{key}:{digest} -->
```

The marker is an HTML comment, so it is invisible when the comment is rendered but visible to any
tool that reads the raw body. It is appended to the body on publish:

```text
Handoff prepared for M-1001

<!-- hidratador:handoff-M-1001:69bbb7e186fa54d9dc20bfc3f1441d687247f92923ce7c7e2314545bc47cb233 -->
```

Because the marker embeds both the key and the digest, matching is exact. A comment carrying the
same key but a different digest is not a match for this entry.

---

## The reconciliation algorithm

`publish()` never blindly resends. For every pending entry, in `created` order:

```text
1. Compute the expected marker for the entry's key and body hash.
2. Read the issue's comments:  gh issue view <issue> --repo R --json comments,url
3. If any comment body contains the exact marker:
     - set state = 'reconciled'
     - record the issue URL
     - report action = 'reconciled', note = 'marker already present; nothing was sent'
     - continue to the next entry
4. If this is a dry run:
     - report action = 'would_publish', note = 'dry run; no comment was written'
     - continue
5. Otherwise:
     - append the marker to the body
     - post:  gh issue comment <issue> --repo R --body <body+marker>
     - set state = 'published' and store the comment URL
     - report action = 'published'
```

Two details matter:

- If the comment read fails for any reason, `_find_marker` returns `None` and the entry is treated
  as not yet posted. A transient read failure does not suppress a write; it only means the marker
  check was inconclusive.
- A reconciled entry is never re-sent. Its state is `reconciled`, not `pending`, so it leaves the
  pending set.

### The result

```json
{
  "repo": "acme/api",
  "dry_run": true,
  "results": [
    {
      "action": "would_publish",
      "issue": 42,
      "key": "handoff-M-1001",
      "note": "dry run; no comment was written"
    }
  ]
}
```

```json
{
  "repo": "acme/api",
  "dry_run": true,
  "results": [
    {
      "action": "reconciled",
      "issue": 42,
      "key": "handoff-M-1001",
      "url": "https://github.com/acme/api/issues/42",
      "note": "marker already present; nothing was sent"
    }
  ]
}
```

### Status

`status(repo=None)` counts what is known:

```json
{
  "repo": "acme/api",
  "observations": 12,
  "actions": ["reconcile_ticket_change", "review_code_change"],
  "outbox": {
    "pending": 1,
    "published": 4,
    "reconciled": 2
  }
}
```

---

## The `gh` boundary

Every `gh` invocation goes through one helper with these limits:

| Limit | Value | Refusal |
|-------|-------|---------|
| Binary present | must be on `PATH` | `AdapterError: gh executable not found on PATH` |
| Timeout | 30 seconds | `AdapterError: gh <subcommand> timed out after 30s` |
| Response size | 16 MiB | `AdapterError: gh response exceeded the 16 MiB limit` |
| Exit status | must be `0` | `AdapterError: gh <subcommand> failed: <stderr, truncated to 400 characters>` |

The invocation is a fixed argv — no shell, no string interpolation of user input into a command
line. `gh` inherits the environment as-is, which means `gh` uses whatever authentication the
operator has already configured. This package neither reads nor stores credentials.

`gh` errors surface as `AdapterError`, which the CLI maps to exit code `3`.

---

## The CLI surface

```bash
# Read-only observation. Without --apply the observations are returned, not stored.
hidratador github-poll --repo acme/api

# Queue and publish. --apply makes it real.
hidratador github-publish --repo acme/api --issue 42 \
  --key handoff-M-1001 --body "Handoff prepared for M-1001"
```

Both commands operate on the **adapter database**, not the ledger. `--db` does not affect them; use
`HIDRATADOR_GITHUB_DB` to relocate that database.

---

## Related pages

- [CLI reference](cli-reference.md) — the two GitHub commands
- [Security](security.md) — the `gh` boundary and the no-credentials rule
- [Operations](operations.md) — where the adapter database lives and how to back it up
