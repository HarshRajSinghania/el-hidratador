"""El Hidratador — the Context Expansion and Execution Staging Engine.

El Hidratador is the bridge between human-approved intent (Ticket Board) and
deterministic machine action (Taskrivet). It hydrates a *dry* semantic ticket
into a *wet* execution packet: expanded context, an ordered execution DAG, a
provisioned sandbox boundary, and a routed compute profile.

Guarantees that hold for the whole package:

* The core is standard-library only — no network, no shell execution, no telemetry.
* Nothing is accepted without an explicit operator decision.
* Every refusal is visible: conflicts, failures, and omitted context are reported.
* Context is untrusted reference data and never authorization.
"""

from __future__ import annotations

from .core import (
    Checkpoint,
    Decision,
    Event,
    Failure,
    FailureCategory,
    Ledger,
    Profile,
    Session,
    Ticket,
    TicketKind,
    TicketStatus,
    create_ledger,
)
from .errors import (
    AdapterError,
    BudgetExceeded,
    Conflict,
    HidratadorError,
    LeaseExpired,
    NotFound,
    ValidationError,
)

__all__ = [
    "AdapterError",
    "BudgetExceeded",
    "Checkpoint",
    "Conflict",
    "Decision",
    "Event",
    "Failure",
    "FailureCategory",
    "HidratadorError",
    "LeaseExpired",
    "Ledger",
    "NotFound",
    "Profile",
    "Session",
    "Ticket",
    "TicketKind",
    "TicketStatus",
    "ValidationError",
    "create_ledger",
    "__version__",
]

__version__ = "0.1.0"
