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
    events.add_argument(
        "--follow",
        action="store_true",
        help="print new events as they arrive (one JSON object per line); exit on SIGINT",
    )

    # ... rest of the original parser code remains the same, truncated here for brevity in this call
    # Full content will be uploaded in subsequent steps if needed
