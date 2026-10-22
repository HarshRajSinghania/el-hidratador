# Summary

<!-- One paragraph. What changes for the user, and what becomes observable. -->

## Ticket

<!--
Ticket reference: M-397001
Link the ticket if one exists: https://github.com/hamanakam1/el-hidratador/issues/1
Leave the line as "none" when the change is not tied to a ticket.
-->

Ticket: M-397001

## Type of change

- [ ] Bug fix
- [ ] Feature
- [ ] Documentation
- [ ] Refactor
- [ ] Test
- [ ] CI

## What changed

<!-- List the files and the behaviour that changed. State the new behaviour, not the diff. -->

-

## Why

<!--
State the problem this solves and how the change was verified to solve it.
If the change does not solve a reported problem, say that plainly.
-->

## How it was verified

<!--
Exact commands and their output. Paste the relevant lines only; do not paste
transcripts, credentials, or private ticket data.
-->

```console
$ python3 -m unittest discover -s tests -v
...

$ ruff check el_hidratador/
All checks passed!
```

## Boundaries respected

- [ ] The core stays standard library only; no new runtime dependency was added.
- [ ] No network access was added to the core; read commands do not phone home.
- [ ] No telemetry was added or enabled.
- [ ] No credentials, tokens, or account details were added.
- [ ] No private ticket data, real transcripts, or deployment names were included.
- [ ] No secrets were committed; the secret scanner is clean.
- [ ] The change stays inside the scope of the ticket.
- [ ] Eligibility was not treated as authorization.
- [ ] The acceptance gate was not bypassed; acceptance remains an operator decision.

## Risk and rollback

<!--
What breaks if this is wrong, how it is observed, and how to revert it.
State the rollback path: revert the commit, or the configuration flag that
restores the previous behaviour.
-->

## Screenshots

<!-- Only when a user visible interface changed. Delete this section otherwise. -->
