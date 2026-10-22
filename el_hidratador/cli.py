"""JSON-first command line interface.

Every command prints one JSON object to stdout. Nothing is written to stdout
that is not machine readable, so the CLI composes with pipes, scripts, and the
local dashboard without parsing prose.

Exit codes:

* ``0`` — the command succeeded
* ``2`` — a refused operation (validation, conflict, budget, lease)
* ``3`` — an adapter failure (GitHub CLI, dashboard, Docker)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .context_expander import expand_from_ledger
from .core import Ledger, create_ledger, default_db_path
from .dag import build_dag, handoff_payload, manifest, summarize
from .dashboard import preview
from .errors import AdapterError, HidratadorError
from .github_sync import GitHubSync
from .hardware_router import default_targets, dispatch_plan, evaluate
from .sandbox import build_sandbox
from .tickets import TicketStore


def _emit(payload: dict[str, Any], pretty: bool = True) -> None:
    text = json.dumps(payload, indent=2 if pretty else None, sort_keys=True, default=str)
    print(text)


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    """Construct the full argument parser."""
    parser = argparse.ArgumentParser(
        prog="hidratador",
        description="El Hidratador — context expansion and execution staging engine.",
    )
    parser.add_argument("--version", action="version", version=f"hidratador {__version__}")
    parser.add_argument(
        "--db",
        default=None,
        help="ledger path (default: $HIDRATADOR_DB or ~/.el-hidratador/ledger.sqlite)",
    )
    parser.add_argument("--compact", action="store_true", help="print JSON on a single line")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the ledger database")
    sub.add_parser("status", help="snapshot the whole ledger")
    sub.add_parser("reconcile", help="expire stale leases and report")
    sub.add_parser("events", help="print audit events")

    events = sub.choices["events"]
    events.add_argument("--after", type=int, default=0)

    task_add = sub.add_parser("task-add", help="create a task")
    task_add.add_argument("id")
    task_add.add_argument("--objective", required=True)
    task_add.add_argument("--acceptance", required=True)
    task_add.add_argument("--title", default="")
    task_add.add_argument("--kind", default="code")
    task_add.add_argument("--scope", action="append", default=[])
    task_add.add_argument("--budget", type=int, default=8000)
    task_add.add_argument("--tags", default="")
    task_add.add_argument("--depends-on", default="")
    task_add.add_argument("--blocks", default="")
    task_add.add_argument("--owner", default="")
    task_add.add_argument("--seed-key", default="")
    task_add.add_argument("--priority", type=int, default=2)
    task_add.add_argument("--description", default="")

    task_show = sub.add_parser("task-show", help="show one task")
    task_show.add_argument("id")

    task_list = sub.add_parser("task-list", help="list tasks")
    task_list.add_argument("--status", default=None)

    triage = sub.add_parser("triage", help="move a task from INBOX to READY")
    triage.add_argument("id")

    start = sub.add_parser("start", help="acquire an execution lease")
    start.add_argument("id")
    start.add_argument("--owner", required=True)
    start.add_argument("--lease", type=int, default=900)

    checkpoint = sub.add_parser("checkpoint", help="record progress with evidence")
    checkpoint.add_argument("session")
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--evidence", required=True)
    checkpoint.add_argument("--next", required=True)
    checkpoint.add_argument("--tokens", type=int, required=True)
    checkpoint.add_argument("--lease", type=int, default=900)

    fail = sub.add_parser("fail", help="record an explicit failure")
    fail.add_argument("session")
    fail.add_argument("--category", required=True)
    fail.add_argument("--summary", required=True)

    finish = sub.add_parser("finish", help="request review")
    finish.add_argument("session")
    finish.add_argument("--evidence", required=True)

    decide = sub.add_parser("decide", help="record an operator decision")
    decide.add_argument("id")
    decide.add_argument("decision", choices=["accept", "retry", "cancel"])
    decide.add_argument("--reason", required=True)

    context_add = sub.add_parser("context-add", help="attach context to a task")
    context_add.add_argument("id")
    source = context_add.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--text")
    context_add.add_argument("--source-label", default="cli")
    context_add.add_argument("--priority", type=int, default=0)
    context_add.add_argument("--ttl", type=int, default=None)

    pack = sub.add_parser("pack", help="build a byte-budgeted execution packet")
    pack.add_argument("id")
    pack.add_argument("--max-bytes", type=int, default=12000)
    pack.add_argument("--packet-only", action="store_true")

    expand = sub.add_parser("expand", help="expand a ticket into a hydrated prompt")
    expand.add_argument("id")
    expand.add_argument("--max-bytes", type=int, default=12000)
    expand.add_argument("--prompt", action="store_true", help="print the prompt only")

    dag_cmd = sub.add_parser("dag", help="build the execution DAG")
    dag_cmd.add_argument("id")

    handoff = sub.add_parser("handoff", help="prepare the Taskrivet handoff payload")
    handoff.add_argument("id")
    handoff.add_argument("--max-bytes", type=int, default=12000)
    handoff.add_argument("--workdir", default=None)

    profile_add = sub.add_parser("profile-add", help="declare a compute profile")
    profile_add.add_argument("id")
    profile_add.add_argument("--kind", action="append", default=[])
    profile_add.add_argument("--context-limit", type=int, required=True)
    profile_add.add_argument("--cost", default="zero_incremental")
    profile_add.add_argument("--ttl", type=int, default=3600)

    route = sub.add_parser("route", help="rank compute targets for a task")
    route.add_argument("id")
    route.add_argument("--required-context", type=int, default=4096)

    export = sub.add_parser("export", help="export tickets to a file-backed store")
    export.add_argument("--dir", default=".hidratador")

    gh_poll = sub.add_parser("github-poll", help="observe a repository (read only)")
    gh_poll.add_argument("--repo", required=True)
    gh_poll.add_argument("--apply", action="store_true", help="persist the observations")

    gh_publish = sub.add_parser("github-publish", help="queue and publish an idempotent comment")
    gh_publish.add_argument("--repo", required=True)
    gh_publish.add_argument("--issue", type=int, required=True)
    gh_publish.add_argument("--key", required=True)
    gh_publish.add_argument("--body", required=True)
    gh_publish.add_argument("--apply", action="store_true", help="publish instead of queueing")

    dash = sub.add_parser("dashboard-preview", help="preview a local dashboard")
    dash.add_argument("--url", required=True)
    dash.add_argument("--status", default="planned")
    dash.add_argument("--offset", type=int, default=0)
    dash.add_argument("--limit", type=int, default=50)

    return parser


def _db_path(args: argparse.Namespace) -> Path:
    if args.db:
        return Path(args.db).expanduser()
    return default_db_path()


def run(argv: Sequence[str] | None = None) -> int:
    """Execute one CLI invocation. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    pretty = not args.compact
    command = args.command

    try:
        if command == "init":
            path = _db_path(args)
            ledger = create_ledger(path)
            payload = {
                "initialized": True,
                "database": str(path),
                "schema_version": ledger.schema_version,
            }
            ledger.close()
            _emit(payload, pretty)
            return 0

        ledger = create_ledger(_db_path(args))
        try:
            handler: Callable[[argparse.Namespace, Ledger], dict[str, Any]] = _HANDLERS[command]
            payload = handler(args, ledger)
            payload.setdefault("ok", True)
            payload["command"] = command
            _emit(payload, pretty)
            return 0
        finally:
            ledger.close()
    except AdapterError as exc:
        _emit({"ok": False, "error": str(exc), "kind": "adapter"}, pretty)
        return 3
    except HidratadorError as exc:
        _emit({"ok": False, "error": str(exc), "kind": type(exc).__name__}, pretty)
        return 2
    except FileNotFoundError as exc:
        _emit({"ok": False, "error": str(exc), "kind": "file"}, pretty)
        return 2


def _cmd_status(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.status()


def _cmd_reconcile(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.reconcile()


def _cmd_events(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    events = ledger.events(after=args.after)
    return {"events": events, "count": len(events)}


def _cmd_task_add(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.add_task(
        task_id=args.id,
        objective=args.objective,
        acceptance=args.acceptance,
        title=args.title,
        kind=args.kind,
        scope=args.scope or None,
        token_budget=args.budget,
        tags=_split(args.tags),
        depends_on=_split(args.depends_on),
        blocks=_split(args.blocks),
        owner=args.owner,
        seed_key=args.seed_key,
        description=args.description,
        priority=args.priority,
    )


def _cmd_task_show(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.task(args.id)


def _cmd_task_list(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    tasks = ledger.tasks(args.status)
    return {"tasks": tasks, "count": len(tasks)}


def _cmd_triage(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.triage(args.id)


def _cmd_start(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.start(args.id, args.owner, args.lease)


def _cmd_checkpoint(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.checkpoint(
        args.session,
        args.summary,
        args.evidence,
        args.next,
        args.tokens,
        args.lease,
    )


def _cmd_fail(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.fail(args.session, args.category, args.summary)


def _cmd_finish(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.finish(args.session, args.evidence)


def _cmd_decide(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.decide(args.id, args.decision, args.reason)


def _cmd_context_add(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    if args.file:
        body = Path(args.file).read_text(encoding="utf-8")
        source = args.source_label if args.source_label != "cli" else args.file
    else:
        body = args.text or ""
        source = args.source_label
    return ledger.add_context(args.id, body, source, args.priority, args.ttl)


def _cmd_pack(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    result = ledger.pack(args.id, args.max_bytes)
    if args.packet_only:
        return {"packet": result["packet"], "packet_bytes": result["packet_bytes"]}
    return result


def _cmd_expand(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    result = expand_from_ledger(ledger, args.id, args.max_bytes)
    if args.prompt:
        return {"task_id": args.id, "prompt": result["prompt"]}
    return {
        "task_id": args.id,
        "prompt": result["prompt"],
        "prompt_bytes": result["prompt_bytes"],
        "packet_bytes": result["packet_bytes"],
        "omitted": result["omitted"],
        "token_estimate": result["token_estimate"],
        "note": result["note"],
    }


def _cmd_dag(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    ticket = ledger.task(args.id)
    dag = build_dag(
        args.id,
        markdown=ticket.get("description", ""),
        ticket_dependencies=ticket.get("depends_on"),
    )
    payload = manifest(dag, ticket)
    payload["summary"] = summarize(dag)
    return payload


def _cmd_handoff(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    ticket = ledger.task(args.id)
    dag = build_dag(
        args.id,
        markdown=ticket.get("description", ""),
        ticket_dependencies=ticket.get("depends_on"),
    )
    expansion = expand_from_ledger(ledger, args.id, args.max_bytes)
    workdir = args.workdir or f"~/.hidratador/work/{args.id}"
    sandbox = build_sandbox(args.id, workdir)
    payload = handoff_payload(dag, expansion["packet"], ticket, sandbox)
    ledger.record_handoff(args.id, payload["manifest"], expansion["packet"])
    return {
        "handoff": payload,
        "prompt": expansion["prompt"],
        "omitted_context": expansion["omitted"],
        "note": "A handoff is prepared state, not permission to execute.",
    }


def _cmd_profile_add(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return ledger.profile(args.id, args.kind, args.context_limit, args.cost, args.ttl)


def _cmd_route(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    ticket = ledger.task(args.id)
    targets = default_targets()
    result = evaluate(ticket, targets, args.required_context)
    payload = result.to_dict()
    payload["plan"] = dispatch_plan(result, args.id)
    return payload


def _cmd_export(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    store = TicketStore(args.dir)
    return store.export_all(ledger.tasks())


def _cmd_github_poll(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    sync = GitHubSync()
    try:
        return sync.poll(args.repo, dry_run=not args.apply)
    finally:
        sync.close()


def _cmd_github_publish(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    sync = GitHubSync()
    try:
        queued = sync.enqueue(args.repo, args.issue, args.key, args.body)
        published = sync.publish(args.repo, dry_run=not args.apply)
        return {"queued": queued, "publish": published}
    finally:
        sync.close()


def _cmd_dashboard_preview(args: argparse.Namespace, ledger: Ledger) -> dict[str, Any]:
    return preview(args.url, args.status, args.offset, args.limit)


_HANDLERS: dict[str, Callable[[argparse.Namespace, Ledger], dict[str, Any]]] = {
    "status": _cmd_status,
    "reconcile": _cmd_reconcile,
    "events": _cmd_events,
    "task-add": _cmd_task_add,
    "task-show": _cmd_task_show,
    "task-list": _cmd_task_list,
    "triage": _cmd_triage,
    "start": _cmd_start,
    "checkpoint": _cmd_checkpoint,
    "fail": _cmd_fail,
    "finish": _cmd_finish,
    "decide": _cmd_decide,
    "context-add": _cmd_context_add,
    "pack": _cmd_pack,
    "expand": _cmd_expand,
    "dag": _cmd_dag,
    "handoff": _cmd_handoff,
    "profile-add": _cmd_profile_add,
    "route": _cmd_route,
    "export": _cmd_export,
    "github-poll": _cmd_github_poll,
    "github-publish": _cmd_github_publish,
    "dashboard-preview": _cmd_dashboard_preview,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by the ``hidratador`` console script."""
    try:
        return run(argv)
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        _emit({"ok": False, "error": "interrupted", "kind": "interrupt"}, True)
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
