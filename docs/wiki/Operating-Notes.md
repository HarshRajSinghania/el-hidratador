# Operating Notes

## Where state lives

| What | Default | Override |
|------|---------|----------|
| Ledger | `~/.el-hidratador/ledger.sqlite` | `HIDRATADOR_DB` |
| GitHub outbox and observations | `~/.el-hidratador/github.sqlite` | `HIDRATADOR_GITHUB_DB` |
| Exported tickets | `.hidratador/` | `hidratador export --dir <path>` |

The ledger is a SQLite database in WAL mode with foreign keys enabled. The
directory is `0700`; the file is `0600`.

## Backup

Stop nothing — WAL mode allows a consistent copy while the ledger is in use:

```bash
sqlite3 ~/.el-hidratador/ledger.sqlite ".backup '/tmp/ledger-backup.sqlite'"
```

Restore by copying the file back and reopening it.

## Reading the event log

```bash
hidratador events --after 0 | jq -r '.events[] | "\(.seq)\t\(.type)\t\(.task_id)"'
```

Every mutation emits an event, including refusals that changed state (lease
expiry, stagnation, budget stops).

## Exporting tickets

```bash
hidratador export --dir ./export
```

Produces `export/tickets/M-1001.md`, `export/index.json`, and
`export/evidence/M-1001/*.json`. It is a portable snapshot — the ledger stays
the authority.

## Reconciling

```bash
hidratador reconcile
```

Expires stale leases and reports the affected tasks. Run it before inspecting
a ledger that might have been open overnight.

## Cost awareness

The ledger reports `reported_tokens` — numbers that workers declared. It does
not measure cash, and `measured_cash_cost` is deliberately `null`.
