# Getting Started

## Install

```bash
git clone git@github.com:hamanakam1/el-hidratador.git
cd el-hidratador
python3 -m pip install -e .
```

Python 3.11 or newer. The core has **no runtime dependencies**.

## Create a ledger

```bash
hidratador init
```

The ledger lives at `~/.el-hidratador/ledger.sqlite` unless `HIDRATADOR_DB`
says otherwise. The directory is created `0700` and the file `0600`.

## The five-minute lifecycle

```bash
# Describe
hidratador task-add M-1001 \
  --objective "Implement JWT-based authentication" \
  --acceptance "Issuance, refresh rotation, and revocation all work" \
  --scope repo/api --scope repo/auth --budget 8000

# Triage and lease
hidratador triage M-1001
hidratador start M-1001 --owner terminal-1 --lease 900

# Work, and record evidence
hidratador checkpoint <session-id> \
  --summary "Implemented token issuance" \
  --evidence "diff 4f2a1c; POST /api/auth/login returns a token pair" \
  --next "Refresh rotation" --tokens 1200

# Request review, then accept
hidratador finish <session-id> --evidence "All endpoints tested"
hidratador decide M-1001 accept --reason "Reviewed the diff and the tests"
```

Every command prints one JSON object. Pipe it into `jq` and keep going.

## Attach context

```bash
hidratador context-add M-1001 --file ./README.md --source-label "repo readme" --priority 10
hidratador expand M-1001 --prompt
```

Attached context is reference data. It is rendered inside explicit
`BEGIN/END UNTRUSTED CONTEXT` banners and is never treated as an instruction.

## Where to go next

- [Architecture](Architecture) for how the pieces fit
- [CLI Cheatsheet](CLI-Cheatsheet) for the full command surface
- [Failure Playbook](Failure-Playbook) when something stops
