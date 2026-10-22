"""Hardware routing and compute dispatch.

The factory is physical: an Apple Silicon host for heavy reasoning, a cluster of
micro-nodes for light staging, and a power budget that is not infinite. Routing
must therefore be explicit about *eligibility* and completely silent about
*authorization* — this module can recommend a target, it can never grant one.

Cost classification is a hard gate. A profile that might bill is never
recommended for autonomous dispatch; it is listed as ineligible with a reason.
"""

from __future__ import annotations

import json
import platform
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import ValidationError

#: Compute classes understood by the router.
CLASS_HEAVY = "heavy"
CLASS_LIGHT = "light"
CLASS_EDGE = "edge"

CLASSES = (CLASS_HEAVY, CLASS_LIGHT, CLASS_EDGE)

#: Context sizes at or above this many bytes are considered heavy reasoning.
HEAVY_CONTEXT_BYTES = 32_000

#: Task kinds that always count as heavy reasoning.
HEAVY_KINDS = ("planning", "closure")


@dataclass
class Target:
    """A compute target that could run a workload."""

    id: str
    class_name: str = CLASS_LIGHT
    context_limit: int = 16_000
    cost: str = "zero_incremental"
    kinds: list[str] = field(default_factory=list)
    healthy: bool = True
    power_ok: bool = True
    verified_until: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class": self.class_name,
            "context_limit": self.context_limit,
            "cost": self.cost,
            "kinds": list(self.kinds),
            "healthy": self.healthy,
            "power_ok": self.power_ok,
            "verified_until": self.verified_until,
            "note": self.note,
        }


@dataclass
class RouteResult:
    """The outcome of a routing decision."""

    task_id: str
    options: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str | None = None
    execution_authorized: bool = False
    provenance: str = "local declaration; no provider telemetry"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "options": self.options,
            "recommendation": self.recommendation,
            "execution_authorized": self.execution_authorized,
            "provenance": self.provenance,
        }


def classify(task: dict[str, Any], context_bytes: int = 0) -> str:
    """Suggest a compute class from the shape of the work."""
    kind = str(task.get("kind", "code"))
    if kind in HEAVY_KINDS:
        return CLASS_HEAVY
    if context_bytes >= HEAVY_CONTEXT_BYTES:
        return CLASS_HEAVY
    return CLASS_LIGHT


def local_topology() -> dict[str, Any]:
    """Describe the host this process runs on. Local facts only."""
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "host": platform.node(),
    }


def evaluate(
    task: dict[str, Any],
    targets: Sequence[Target],
    required_context: int = 4096,
    now: float | None = None,
) -> RouteResult:
    """Evaluate every target for a task. Eligibility is never authorization."""
    if type(required_context) is not int or required_context <= 0:
        raise ValidationError("required_context must be a positive integer")
    moment = time.time() if now is None else now
    task_id = str(task.get("id", ""))
    kind = str(task.get("kind", "code"))
    desired = classify(task, int(task.get("context_bytes", 0) or 0))

    options: list[dict[str, Any]] = []
    for target in targets:
        reasons: list[str] = []
        if kind not in target.kinds:
            reasons.append("task kind unsupported")
        if target.context_limit < required_context:
            reasons.append("insufficient declared context capacity")
        if target.cost != "zero_incremental":
            reasons.append("new spending is not authorized or cost is unknown")
        if not target.healthy:
            reasons.append("target reported unhealthy")
        if not target.power_ok:
            reasons.append("target is power constrained")
        if target.verified_until and target.verified_until <= moment:
            reasons.append("target declaration expired")
        if target.class_name != desired:
            reasons.append(f"workload class is {desired}; target class is {target.class_name}")
        options.append(
            {
                "target": target.id,
                "class": target.class_name,
                "eligible": not reasons,
                "reasons": reasons,
                "cost": target.cost,
                "context_limit": target.context_limit,
                "quality_estimate": None,
                "provenance": "local declaration; no provider telemetry",
            }
        )

    eligible = [option for option in options if option["eligible"]]
    recommendation = eligible[0]["target"] if eligible else None
    return RouteResult(
        task_id=task_id,
        options=options,
        recommendation=recommendation,
        execution_authorized=False,
    )


def dispatch_plan(result: RouteResult, task_id: str, dry_run: bool = True) -> dict[str, Any]:
    """Render the dispatch plan for a routing result.

    A plan is a document. Executing it is a separate, explicit action that
    this package deliberately does not take.
    """
    payload = {
        "task_id": task_id,
        "target": result.recommendation,
        "options": result.options,
        "dry_run": dry_run,
        "execution_authorized": False,
        "provenance": result.provenance,
        "note": "Dispatch requires an operator decision; the router never starts work.",
    }
    payload["plan_hash"] = _hash(payload)
    return payload


def _hash(payload: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]


def default_targets() -> list[Target]:
    """A conservative local target set. Everything is unverified."""
    return [
        Target(
            id="local-heavy",
            class_name=CLASS_HEAVY,
            context_limit=64_000,
            cost="zero_incremental",
            kinds=["code", "fix", "planning", "closure", "product"],
            note="Apple silicon host; unified memory for local inference",
        ),
        Target(
            id="local-light",
            class_name=CLASS_LIGHT,
            context_limit=16_000,
            cost="zero_incremental",
            kinds=["code", "fix", "product"],
            note="Micro-node staging for parallel background scripts",
        ),
        Target(
            id="edge-staging",
            class_name=CLASS_EDGE,
            context_limit=4_000,
            cost="zero_incremental",
            kinds=["code", "fix"],
            note="Raspberry Pi cluster; provisioning and repository cloning only",
        ),
    ]
