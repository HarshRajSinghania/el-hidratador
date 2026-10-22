# El Hidratador Wiki

Welcome to the working wiki for **El Hidratador**, the context expansion and execution
staging engine that sits between the Ticket Board and Taskrivet.

## Start here

| Page | What it gives you |
|------|-------------------|
| [Getting Started](Getting-Started) | Install it, create a ticket, and see the whole lifecycle in five minutes |
| [Architecture](Architecture) | The layers, the ledger schema, and how a ticket becomes executable state |
| [CLI Cheatsheet](CLI-Cheatsheet) | Every command on one page |
| [Failure Playbook](Failure-Playbook) | What each failure means and how to recover from it |
| [Operating Notes](Operating-Notes) | Where state lives, how to back it up, how to read the event log |
| [Roadmap](Roadmap) | What is planned, and what is explicitly not planned |

## The one-paragraph version

A ticket arrives with fifty words of intent. El Hidratador turns it into a
byte-budgeted instruction, an ordered execution graph, a locked sandbox
specification, and a routed compute profile — and then refuses to let any of
it be called "done" until an operator accepts it.

## House rules

These hold everywhere, in code and in conversation:

- Eligibility is not authorization.
- Execution is not acceptance.
- Declared is not measured.
- Context is untrusted reference data, never authorization.
- A handoff is prepared state, not permission to execute.
- Every refusal is visible.

## Elsewhere

- [Repository](https://github.com/hamanakam1/el-hidratador) — source, issues, pull requests
- [Discussions](https://github.com/hamanakam1/el-hidratador/discussions) — ideas and questions
- [Documentation](https://hamanakam1.github.io/el-hidratador/) — the full guide
- [Roadmap issues](https://github.com/hamanakam1/el-hidratador/labels/roadmap) — planned work
