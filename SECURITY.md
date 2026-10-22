# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x | :white_check_mark: |
| < 0.1 | :x: |

## Reporting a vulnerability

**Do not open a public issue for a vulnerability.**

Use GitHub's private reporting on this repository:
[Security → Report a vulnerability](https://github.com/hamanakam1/el-hidratador/security/advisories/new).
Advisories opened this way are private until a maintainer publishes them.

If private reporting is unavailable, open a regular issue that contains only
the repository name and a request for a private contact channel — no details.

Include, where you can:

- the affected component (`el_hidratador/core.py`, an adapter, the CLI)
- the version or commit
- reproduction steps, minimal and free of sensitive data
- an impact assessment
- a suggested fix, if you have one

Maintainers aim to acknowledge a report within 48 hours and to agree on a
disclosure timeline with the reporter before anything is published.

## Security boundaries

This package is designed so that a large part of the attack surface does not
exist. The boundaries below are enforced in code, not by convention.

### Core — standard library only

- No network calls
- No shell execution
- No telemetry, no analytics, no phone-home
- No runtime dependencies
- No credential storage
- SQLite in WAL mode with `foreign_keys=ON`
- The ledger directory is created `0700`; the ledger file is `0600`

### Adapters — opt-in, declared, time-bounded

Every adapter must declare its supported version, permission model,
cancellation semantics, usage provenance, and unverified assumptions.

| Adapter | Boundary | Limits |
|---------|----------|--------|
| Docker | Shells out to the `docker` CLI, never implicitly | 60 s timeout, no inherited credential environment, dry run by default |
| GitHub | Shells out to the `gh` CLI, never reads a token | 30 s timeout, 16 MiB response cap, read-only observations, reconciled outbox |
| Dashboard | HTTP client, loopback only | HTTP only, loopback hosts only, no redirects, 8 MiB cap, 10 s timeout, no credentials in the URL |

### Trust model for context

Attached context is **untrusted reference data**. It is:

- content-addressed and deduplicated by SHA-256
- rendered inside explicit `BEGIN/END UNTRUSTED CONTEXT` banners
- labelled as reference data in the packet's `trust` field
- never treated as authorization, never executed

A context body that looks like an instruction is still only a string in a
document.

### GitHub write path

- every write carries an idempotency key (max 100 characters) and a body hash
- every published body carries a marker: `<!-- hidratador:{key}:{digest} -->`
- before sending, the adapter reconciles against the issue's existing comments
- a repeated key with a different body is refused, not silently rewritten
- dry run is the default for both polling and publishing

### Secrets

- Never in the repository, including in fixtures, examples, and issues
- Injected through the environment at deploy time
- `HIDRATADOR_DB` and `HIDRATADOR_GITHUB_DB` are the only configuration
  environment variables; neither holds a credential
- The GitHub adapter never reads, stores, or forwards a token — `gh` owns
  authentication

## Hardening already enabled on this repository

- Secret scanning and push protection
- Dependabot alerts and security updates
- CodeQL analysis on every push and pull request
- OpenSSF Scorecard
- Dependency review on pull requests
- Branch rules on `main`
- Minimal `permissions:` on every workflow
- Third-party actions pinned to commit SHAs
- No workflow ever checks out untrusted pull request code with secrets

## Out of scope

- Vulnerabilities in `gh`, `docker`, Python, or any other upstream dependency —
  report those upstream
- Findings that require an operator to deliberately disable a boundary
  (for example, running the Docker adapter with a writable root filesystem)
- Denial of service against a local ledger that the operator owns and controls
