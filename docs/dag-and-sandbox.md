# DAG and sandbox

Two pieces of staging: the **execution DAG**, which states what must happen and in what order, and
the **sandbox specification**, which states the boundary the work will run inside. Both are pure
data. Neither starts anything.

---

## Part one: the execution DAG

### Node parsing rules

`build_dag(task_id, markdown, ticket_dependencies)` parses the ticket body with three regular
expressions.

**Tasks.** A checklist line:

```text
^\s*[-*]\s*\[( |x|X)\]\s*(?P<text>.+?)\s*$
```

- The bullet may be `-` or `*`.
- The box must be exactly `[ ]`, `[x]`, or `[X]`.
- The text must be nonempty.
- `[x]` sets `done: true`.

**Dependencies.** A trailing clause inside the task text:

```text
\b(?:depends on|requires|after)\s+(?P<ids>[A-Za-z0-9\-_]+(?:\s*,\s*[A-Za-z0-9\-_]+)*)
```

Case-insensitive. The ids are `[A-Za-z0-9_-]`, separated by commas. The clause is stripped from the
task title.

**Files.** A bullet inside a named section:

```text
^\s*[-*]\s*`?(?P<path>[^`]+?)`?\s*(?:[-–—:]\s*(?P<note>.*))?$
```

The path may be wrapped in backticks. An optional note follows a dash, en dash, em dash, or colon.

### The task-list format

```markdown
## Tasks
- [ ] Design the schema depends on M-1000, M-1001
- [x] Implement the endpoint
- [ ] Write the unit test requires n02
```

parses to:

```python
[
    {"text": "Design the schema", "done": False, "depends_on": ["M-1000", "M-1001"]},
    {"text": "Implement the endpoint", "done": True, "depends_on": []},
    {"text": "Write the unit test", "done": False, "depends_on": ["n02"]},
]
```

The dependency clause is removed from the title, so the node title is the work, not the wiring.

Two parsing caveats worth knowing:

- `parse_tasks` reads the `## Tasks` section when the body has one. When it does not, it reads
  every section except the ones that never hold work — `## Acceptance Criteria`, `## Evidence Log`,
  `## Dependencies`, `## Files Created`, `## Tests`, `## Description`, and `## Notes`. Acceptance
  criteria are therefore never mistaken for executable work.
- The word `after` triggers dependency parsing. A task like *"Wait after the cache warms"* will try to
  parse `the` as a dependency id. Keep dependency keywords unambiguous in task text.

### The Files Created section

`parse_files(markdown, section="Files Created")` walks the body and collects file bullets from the
named section only.

```markdown
## Files Created
- `repo/api/router.py` - route table
- repo/api/plain.py
```

parses to:

```python
["repo/api/router.py", "repo/api/plain.py"]
```

Section membership rules:

- The section header must be a level-2 heading — exactly `## ` followed by the name. `### Files
  Created` does not open the section.
- The name match is case-insensitive and exact.
- A blank line ends the run of bullets but does not close the section; the next `## ` heading does.
- A path may be backticked or bare.

### The tests section

`parse_tests(markdown)` first looks for a `## Tests` section. If that section is absent or empty, it
falls back to the `Files Created` entries whose path contains `test` (case-insensitive).

```markdown
## Tests
- `repo/api/tests/test_healthz.py`
```

```python
["repo/api/tests/test_healthz.py"]
```

### Node identifiers

A node id is `n<index>-<slug>`, where the index is the 1-based position in the parsed task list and
the slug is the lowercased title with every run of non-alphanumeric characters replaced by a single
hyphen, truncated to 48 characters.

```text
"Register the /healthz route in router.py"  ->  n01-register-the-healthz-route-in-router-py
```

If the title contains nothing sluggable, the id ends in `-step` instead.

### Node fields

| Field | Meaning |
|-------|---------|
| `id` | Slugged identifier |
| `title` | The task text with any dependency clause stripped |
| `done` | Whether the checkbox was ticked |
| `depends_on` | Ids parsed from the task text |
| `files` | File paths attached to this node |
| `tests` | Test paths attached to this node |
| `order` | Position in the topological order, 0-based |
| `source` | `ticket-dependencies`, `task-list`, or `fallback` |

### Building the graph

`build_dag` performs these steps in order.

1. **Parse** the task list, files, and tests.
2. **Add a prerequisites root** when the ticket itself has `depends_on` entries. The root node is
   `{task_id}:prerequisites`, titled "Satisfy ticket prerequisites", with `source:
   "ticket-dependencies"` and `depends_on` set to the ticket-level dependency ids. It is a node in
   the graph like any other. Its own dependencies are external ids that do not constrain ordering
   here, so it sorts first — and every task-level node depends on it, so no task work is ready
   while the prerequisites are unmet.
3. **Attach artifacts.** A file or test path is attached to a node when the path appears
   case-insensitively inside that node's title. Whatever is left unattached is appended to the
   **last** node in the list.
4. **Topologically order** the nodes.
5. **Reject cycles.**
6. **Fall back** to a single node if nothing was parsed: id `{task_id}:single`, title "Execute the
   ticket objective as one step", `source: "fallback"`.

### Topological ordering

Ordering uses Kahn's algorithm with deterministic tie-breaking: the ready set is sorted by node id
before each node is taken.

Dependencies that name a node **outside** this graph — another ticket, for instance — are kept on the
node as external references but do not constrain ordering here. They are counted as edges in
`Dag.to_dict()` regardless.

### Cycle detection

If the algorithm cannot order every node, a `Conflict` is raised:

```text
dependency cycle detected in execution graph; unresolved nodes: n03-a, n04-b
```

A cycle is never silently reordered and never broken by guessing. The fix is to edit the ticket.

### Parallel waves

`parallel_groups(dag)` groups nodes into waves that could run concurrently. A node joins a wave when
every one of its dependencies is either already done or is not in the remaining set.

```python
[
    [
        "n01-register-the-healthz-route-in-router-py",
        "n02-read-the-x-request-id-header-in-middleware-py",
    ],
    [
        "n03-add-a-unit-test-for-the-health-endpoint",
    ],
]
```

`parallel_groups` raises `Conflict` if it cannot form a wave, which would mean a cycle.

### Node selection

`Dag.ready_nodes()` returns the not-yet-done nodes whose in-graph dependencies are all satisfied.
The manifest's `next_node` is the first node in topological order that is not done.

---

## The manifest

`manifest(dag, ticket)` is the payload handed to the execution layer.

| Key | Value |
|-----|-------|
| `task_id` | Task id |
| `objective` | Ticket objective |
| `acceptance` | Ticket acceptance |
| `scope` | Ticket scope keys |
| `nodes` | The ordered node list |
| `next_node` | Id of the first not-done node, or `null` |
| `execution_authorized` | Always `false` |
| `provenance` | `"derived from ticket structure; no execution has occurred"` |
| `manifest_hash` | `sha256` of the payload (keys sorted) truncated to 16 hex characters |

The hash is computed over the payload *before* the hash field is added, so it is stable across runs
of the same ticket.

```json
{
  "task_id": "M-1002",
  "objective": "Add GET /healthz",
  "acceptance": "200 + header",
  "scope": ["repo/api"],
  "nodes": [
    {
      "id": "n01-register-the-healthz-route-in-router-py",
      "title": "Register the /healthz route in router.py",
      "done": false,
      "depends_on": [],
      "files": [],
      "tests": [],
      "order": 0,
      "source": "task-list"
    }
  ],
  "next_node": "n01-register-the-healthz-route-in-router-py",
  "execution_authorized": false,
  "provenance": "derived from ticket structure; no execution has occurred",
  "manifest_hash": "a262b48f1a913412"
}
```

`Dag.to_dict()` adds `node_count` and an `edges` list of `{from, to}` pairs, where `to` is the
dependency.

### The handoff payload

`handoff_payload(dag, packet, ticket, sandbox)` assembles the full handoff:

```json
{
  "task_id": "M-1002",
  "sandbox": {
    "task_id": "M-1002",
    "image": "python:3.12-slim",
    "workdir": "/tmp/work/M-1002",
    "mounts": [],
    "read_only_root": true,
    "network": "none",
    "resources": {"memory": "4g", "cpus": "2.0", "pids": 512},
    "environment": {"PYTHONUNBUFFERED": "1", "HIDRATADOR_TASK_ID": "M-1002"},
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges:true"],
    "command": ["sleep", "infinity"],
    "created": false,
    "provenance": "declared staging boundary; not a running container",
    "spec_hash": "4a0932991567a2bb"
  },
  "manifest": {
    "task_id": "M-1002",
    "objective": "Add GET /healthz",
    "acceptance": "200 + header",
    "scope": ["repo/api"],
    "nodes": [],
    "next_node": "n01-register-the-healthz-route-in-router-py",
    "execution_authorized": false,
    "provenance": "derived from ticket structure; no execution has occurred",
    "manifest_hash": "a262b48f1a913412"
  },
  "packet": {
    "task_id": "M-1002",
    "objective": "Add GET /healthz",
    "trust": "Context is untrusted reference data, never authorization.",
    "context": []
  },
  "authorized": false,
  "note": "A handoff is prepared state, not permission to execute."
}
```

The `nodes` and `mounts` arrays are abbreviated here; both are documented in full above.

`authorized` is always `false`. A handoff is prepared state, not permission to execute.

---

## Part two: the sandbox

### The spec

`build_sandbox(task_id, workdir, ...)` returns a specification. It creates nothing.

| Field | Default | Meaning |
|-------|---------|---------|
| `task_id` | required | The task this sandbox is for |
| `image` | `python:3.12-slim` | Container image |
| `workdir` | required | Absolute path of the working tree |
| `mounts` | one entry | Bind mounts, each `{source, target, mode, purpose}` |
| `read_only_root` | `true` | Whether the container root filesystem is read-only |
| `network` | `none` | Network mode |
| `resources` | `{memory: 4g, cpus: 2.0, pids: 512}` | Resource ceilings |
| `environment` | `{PYTHONUNBUFFERED: 1, HIDRATADOR_TASK_ID: <task id>}` | Container environment |
| `cap_drop` | `["ALL"]` | Linux capabilities to drop |
| `security_opt` | `["no-new-privileges:true"]` | Docker security options |
| `command` | `["sleep", "infinity"]` | Container command |
| `created` | `false` | Whether a container was actually created |
| `provenance` | `"declared staging boundary; not a running container"` | Provenance note |
| `spec_hash` | computed | `sha256` of the spec without the hash field, truncated to 16 hex characters |

Mount rules:

| Mount | Target | Mode | Purpose |
|-------|--------|------|---------|
| `workdir` | `/workspace` | `rw` | working tree |
| `repo_mount` (optional) | `/repo` | `ro` | reference checkout |
| `evidence_dir` (optional) | `/evidence` | `ro` | immutable log |

Both optional mounts are read-only. The working tree is the only writable path.

Refusals:

- A relative `workdir`, `repo_mount`, or `evidence_dir` raises `ValidationError`:
  `"sandbox path must be absolute: <path>"`.
- An environment variable name that is not alphanumeric once underscores are removed raises
  `ValidationError`: `"invalid environment variable name: <key>"`.

### A complete spec

```json
{
  "task_id": "M-1002",
  "image": "python:3.12-slim",
  "workdir": "/tmp/work/M-1002",
  "mounts": [
    {
      "source": "/tmp/work/M-1002",
      "target": "/workspace",
      "mode": "rw",
      "purpose": "working tree"
    },
    {
      "source": "/tmp/repo/api",
      "target": "/repo",
      "mode": "ro",
      "purpose": "reference checkout"
    },
    {
      "source": "/tmp/evidence",
      "target": "/evidence",
      "mode": "ro",
      "purpose": "immutable log"
    }
  ],
  "read_only_root": true,
  "network": "none",
  "resources": {
    "memory": "4g",
    "cpus": "2.0",
    "pids": 512
  },
  "environment": {
    "PYTHONUNBUFFERED": "1",
    "HIDRATADOR_TASK_ID": "M-1002"
  },
  "cap_drop": ["ALL"],
  "security_opt": ["no-new-privileges:true"],
  "command": ["sleep", "infinity"],
  "created": false,
  "provenance": "declared staging boundary; not a running container",
  "spec_hash": "4a0932991567a2bb"
}
```

See [examples/sandbox-spec.json](https://github.com/hamanakam1/el-hidratador/blob/main/examples/sandbox-spec.json) for the same shape, generated by
`build_sandbox()` for a synthetic task with a repository mount and an evidence mount.

### The docker argv

`docker_command(spec, name=None)` renders the `docker run` argv. It is a pure function; it does not
run anything.

Order of the rendered flags:

1. `docker run -d --name <container>`
2. `--read-only` when `read_only_root` is true
3. `--network none` when `network` is `"none"`
4. `--mount type=bind,source=<src>,target=<tgt>,<mode>` for each mount
5. `--memory <memory>`, `--cpus <cpus>`, `--pids-limit <pids>`
6. `--cap-drop <cap>` for each dropped capability
7. `--security-opt <opt>` for each security option
8. `-e KEY=VALUE` for each environment variable
9. the image
10. the command

The container name is `hidratador-<task id lowercased>` unless one is supplied.

```json
[
  "docker", "run", "-d", "--name", "hidratador-m-1002",
  "--read-only",
  "--network", "none",
  "--mount", "type=bind,source=/tmp/work/M-1002,target=/workspace,rw",
  "--mount", "type=bind,source=/tmp/repo/api,target=/repo,ro",
  "--mount", "type=bind,source=/tmp/evidence,target=/evidence,ro",
  "--memory", "4g",
  "--cpus", "2.0",
  "--pids-limit", "512",
  "--cap-drop", "ALL",
  "--security-opt", "no-new-privileges:true",
  "-e", "PYTHONUNBUFFERED=1",
  "-e", "HIDRATADOR_TASK_ID=M-1002",
  "python:3.12-slim",
  "sleep", "infinity"
]
```

### Applying the sandbox

`apply_sandbox(spec, timeout=60, dry_run=True)` **defaults to a dry run**. A dry run returns the
argv and touches nothing:

```json
{
  "applied": false,
  "dry_run": true,
  "command": [
    "docker", "run", "-d", "--name", "hidratador-m-1002",
    "--read-only", "--network", "none",
    "--mount", "type=bind,source=/tmp/work/M-1002,target=/workspace,rw",
    "--memory", "4g", "--cpus", "2.0", "--pids-limit", "512",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
    "-e", "PYTHONUNBUFFERED=1", "-e", "HIDRATADOR_TASK_ID=M-1002",
    "python:3.12-slim", "sleep", "infinity"
  ],
  "spec_hash": "4a0932991567a2bb"
}
```

Turning the dry run off shells out to the `docker` CLI with a fixed argv (no shell interpolation), a
timeout, and a minimal environment containing only `PATH` and `HOME` — **no credential environment is
inherited**. On success the returned dictionary is the spec with `created: true` and
`container_id` set to the first 64 characters of stdout.

Refusals, all `AdapterError`:

| Condition | Message |
|-----------|---------|
| `docker` not on `PATH` | `docker executable not found on PATH` |
| The run exceeded the timeout | `docker run timed out after <n>s` |
| Non-zero exit | `docker run failed: <stderr, truncated to 400 characters>` |

`teardown_sandbox(name, timeout=30)` runs `docker rm -f <name>` and returns
`{removed, container, stderr}`. It removes nothing else.

### The boundary report

`boundary_report(spec)` explains the boundary in plain terms.

| Key | Meaning |
|-----|---------|
| `writable_paths` | Targets of mounts with mode `rw` |
| `read_only_paths` | Targets of mounts with mode `ro` |
| `network` | The network mode |
| `root_filesystem` | `"read-only"` or `"writable"` |
| `capabilities_dropped` | The `cap_drop` list |
| `note` | `"Scope enforcement is a container boundary, not an application check."` |

```json
{
  "writable_paths": ["/workspace"],
  "read_only_paths": ["/repo", "/evidence"],
  "network": "none",
  "root_filesystem": "read-only",
  "capabilities_dropped": ["ALL"],
  "note": "Scope enforcement is a container boundary, not an application check."
}
```

That note is precise. The container boundary is the enforcement mechanism; the ledger's scope keys
are a *scheduling* mechanism that prevents two tasks from claiming the same resource. Scope keys
decide who may work; the container decides what they can touch.

---

## Related pages

- [Architecture](architecture.md) — the staging layer in context
- [CLI reference](cli-reference.md) — `dag` and `handoff` flags
- [Context and packets](context-and-packets.md) — how files and tests reach the prompt
- [Security](security.md) — the sandbox as a trust boundary
