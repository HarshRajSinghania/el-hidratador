# Contributing to El Hidratador

Thanks for taking the time. This repository is small on purpose, and the rules
below are the same rules the code follows.

## Before you start

- **Search first.** Issues, discussions, and the `roadmap` label track what is
  planned. A short conversation in [Discussions](https://github.com/hamanakam1/el-hidratador/discussions)
  is cheaper than a large pull request that gets closed.
- **Open an issue** describing an observable user outcome. A pull request
  without a stated outcome is hard to review.
- **Claim the scope.** Resource scope keys are how two workers avoid
  colliding. If your change touches a module, say which scope key it owns.

## The rules that matter

**Do not conflate:**

- eligible routing with authorization
- a finished session with accepted work
- declared usage with measured billing
- ledger checks with process isolation
- prepared state with permission to execute

**Do preserve:**

- the acceptance gate — nothing becomes `DONE` without `decide(accept)`
- the byte budget — omitted context is always reported
- the untrusted-context boundary — attached context is reference data
- the core's isolation — no network, no shell execution, no telemetry
- lease exclusivity — overlapping scopes never run at the same time
- event log completeness — every mutation emits an event

**Do not:**

- add network calls or telemetry to read commands
- add runtime dependencies to the core; it is standard library only
- put credentials, tokens, transcripts, or real ticket data in the repository
- publish internal hostnames, deployment names, or local installation paths
- bypass `decide(accept)` with a shortcut, a default, or a flag
- report a token count as if a provider had measured it

## Development

```bash
python3 -m pip install -e ".[dev]"

make test        # python3 -m unittest discover -s tests -v
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy el_hidratador/
make check       # everything the CI runs
```

Python 3.11 or newer. The test suite must pass on Linux and macOS, on 3.11
through 3.14.

## Pull requests

1. **One outcome per pull request.** Mixed refactors make review impossible.
2. **Add tests that would fail without your change.** Concurrency, failure
   recovery, and budget boundaries need explicit coverage.
3. **Document schema changes.** State the migration, and make it additive and
   idempotent.
4. **Describe adapter changes fully:** supported versions, permission model,
   usage provenance, cancellation semantics, and unverified assumptions. A
   small qualified adapter beats a long list of nominal integrations.
5. **Update the docs you changed.** `docs/` and `examples/` are part of the
   product, not an afterthought.
6. **Keep the changelog honest.** `CHANGELOG.md` is written for the person who
   upgrades, not for the person who commits.

### Commit and branch naming

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat(dag): detect cycles across ticket-level dependencies
fix(core): release the scope reservation when a lease expires
docs(failure-playbook): document the no-progress recovery path
```

Branch names: `feat/…`, `fix/…`, `docs/…`, `chore/…`.

## Adding an adapter

An adapter is anything that leaves the core boundary. It must declare:

| Declaration | Meaning |
|-------------|---------|
| Supported version | Which version of the external tool is known to work |
| Permission model | What the adapter is allowed to do, and what it refuses |
| Cancellation semantics | How a partial operation is abandoned |
| Usage provenance | Where reported numbers come from, and who measured them |
| Unverified assumptions | What has not been tested and might be wrong |

Adapters must be opt-in, time-bounded, and must never persist credentials.

## Security

Do not open a public issue for a vulnerability. Follow
[SECURITY.md](SECURITY.md) — GitHub private vulnerability reporting is enabled
on this repository.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

Contributions are accepted under the [MIT License](LICENSE).
