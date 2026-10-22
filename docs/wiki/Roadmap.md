# Roadmap

The repository [roadmap label](https://github.com/hamanakam1/el-hidratador/labels/roadmap)
is the source of truth. This page explains the shape of the plan.

## Now — v0.1.x

- The ledger, the hydration pipeline, and the staging boundary.
- The JSON-first command line interface.
- GitHub observations and the reconciled outbox.

## Next — v0.2.0

- Code-derived DAG hints: suggest node structure from the repository instead
  of only from the ticket body.
- Context ranking that uses observed usefulness rather than declared priority.
- A first published handoff contract with Taskrivet.
- Profile outcome evidence, so routing can rank eligible targets.

## Later — v0.3.0

- Multi-node staging with health-aware placement.
- Measured usage reporting where a provider actually meters it.
- A replayable run log: reconstruct any session from its events.

## Not planned

These are deliberate refusals, not gaps:

- No automatic acceptance. Nothing reaches `DONE` without an operator.
- No cloud dispatch. A paid profile is never eligible for autonomous work.
- No multi-tenant ledger. One ledger belongs to one factory.
- No telemetry. The core has no way to report home.
- No automatic dependency installation in the core. That belongs in the sandbox
  adapter, where it is visible.
