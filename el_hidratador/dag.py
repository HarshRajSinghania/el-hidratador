"""Execution DAG generation.

Before anything executes, the order of work must be explicit. This module turns
a hydrated ticket into a directed acyclic graph of nodes, each with its
dependencies, the files it touches, and the tests it must satisfy.

Properties that matter:

* The graph is deterministic. The same ticket always produces the same node
  order, so manifests can be diffed and hashed.
* Cycles are a hard error, never a silent reordering.
* A manifest states what *must* happen; it never implies that it *has* happened.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .errors import Conflict, ValidationError

TASK_LINE = re.compile(r"^\s*[-*]\s*\[( |x|X)\]\s*(?P<text>.+?)\s*$")
FILE_LINE = re.compile(r"^\s*[-*]\s*`?(?P<path>[^`]+?)`?\s*(?:[-–—:]\s*(?P<note>.*))?$")
DEP_LINE = re.compile(
    r"\b(?:depends on|requires|after)\s+(?P<ids>[A-Za-z0-9\-_]+(?:\s*,\s*[A-Za-z0-9\-_]+)*)",
    re.IGNORECASE,
)


@dataclass
class Node:
    """One unit of work in the execution graph."""

    id: str
    title: str
    done: bool = False
    depends_on: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    order: int = 0
    source: str = "task-list"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "done": self.done,
            "depends_on": list(self.depends_on),
            "files": list(self.files),
            "tests": list(self.tests),
            "order": self.order,
            "source": self.source,
        }


@dataclass
class Dag:
    """An ordered, acyclic execution graph."""

    task_id: str
    nodes: list[Node] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "node_count": len(self.nodes),
            "edges": [
                {"from": node.id, "to": dep} for node in self.nodes for dep in node.depends_on
            ],
        }

    def ready_nodes(self) -> list[Node]:
        """Nodes whose in-graph dependencies are already satisfied."""
        known = {node.id for node in self.nodes}
        done = {node.id for node in self.nodes if node.done}
        return [
            node
            for node in self.nodes
            if not node.done and all(dep in done for dep in node.depends_on if dep in known)
        ]


def _slug(text: str, index: int) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return f"n{index:02d}-{cleaned[:48]}" if cleaned else f"n{index:02d}-step"


def parse_tasks(markdown: str) -> list[dict[str, Any]]:
    """Extract checklist items from a ticket body."""
    tasks: list[dict[str, Any]] = []
    for line in (markdown or "").splitlines():
        match = TASK_LINE.match(line)
        if match:
            text = match.group("text").strip()
            deps: list[str] = []
            dep_match = DEP_LINE.search(text)
            if dep_match:
                deps = [part.strip() for part in dep_match.group("ids").split(",") if part.strip()]
                text = DEP_LINE.sub("", text).strip(" —-:")
            tasks.append({"text": text, "done": match.group(1).lower() == "x", "depends_on": deps})
    return tasks


def parse_files(markdown: str, section: str = "Files Created") -> list[str]:
    """Extract file paths from a named markdown section."""
    lines = (markdown or "").splitlines()
    collected: list[str] = []
    inside = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("## "):
            inside = stripped[3:].strip().lower() == section.lower()
            continue
        if not inside or not stripped:
            continue
        match = FILE_LINE.match(stripped)
        if match:
            path = match.group("path").strip()
            if path:
                collected.append(path)
    return collected


def parse_tests(markdown: str) -> list[str]:
    """Extract test paths from a 'Tests' section, falling back to 'Files Created'."""
    tests = parse_files(markdown, "Tests")
    if not tests:
        tests = [path for path in parse_files(markdown, "Files Created") if "test" in path.lower()]
    return tests


def build_dag(
    task_id: str,
    markdown: str = "",
    ticket_dependencies: Sequence[str] | None = None,
    files: Sequence[str] | None = None,
    tests: Sequence[str] | None = None,
) -> Dag:
    """Build the execution graph for a ticket.

    Ticket-level dependencies become a root node so that every task-level node
    inherits the same prerequisites.
    """
    if not task_id:
        raise ValidationError("task_id must be nonempty")
    task_list = parse_tasks(markdown)
    file_list = list(files or []) or parse_files(markdown)
    test_list = list(tests or []) or parse_tests(markdown)
    ticket_deps = [str(dep) for dep in (ticket_dependencies or [])]

    nodes: list[Node] = []
    if ticket_deps:
        root = Node(
            id=f"{task_id}:prerequisites",
            title="Satisfy ticket prerequisites",
            depends_on=list(ticket_deps),
            source="ticket-dependencies",
        )
        nodes.append(root)

    for index, item in enumerate(task_list, start=1):
        node = Node(
            id=_slug(item["text"], index),
            title=item["text"],
            done=item["done"],
            depends_on=list(item["depends_on"]),
            source="task-list",
        )
        nodes.append(node)

    if not nodes:
        node = Node(
            id=f"{task_id}:single",
            title="Execute the ticket objective as one step",
            source="fallback",
        )
        nodes.append(node)

    _attach_artifacts(nodes, file_list, test_list)
    order = _topological_order(nodes)
    for position, node in enumerate(order):
        node.order = position
    return Dag(task_id=task_id, nodes=order)


def _attach_artifacts(nodes: list[Node], files: Sequence[str], tests: Sequence[str]) -> None:
    """Attach files and tests to nodes using explicit path hints."""
    for node in nodes:
        for path in files:
            if path.lower().replace("\\", "/") in node.title.lower().replace("\\", "/"):
                node.files.append(path)
        for path in tests:
            if path.lower().replace("\\", "/") in node.title.lower().replace("\\", "/"):
                node.tests.append(path)
    if files and nodes:
        nodes[-1].files.extend(path for path in files if path not in nodes[-1].files)
    if tests and nodes:
        nodes[-1].tests.extend(path for path in tests if path not in nodes[-1].tests)


def _topological_order(nodes: list[Node]) -> list[Node]:
    """Kahn's algorithm with deterministic tie-breaking. Cycles raise.

    Dependencies that name a node outside this graph (another ticket) are kept
    on the node as external references but do not constrain ordering here.
    """
    by_id: dict[str, Node] = {node.id: node for node in nodes}
    indegree: dict[str, int] = {node.id: 0 for node in nodes}
    dependents: dict[str, list[str]] = {node.id: [] for node in nodes}

    for node in nodes:
        for dep in node.depends_on:
            if dep in by_id:
                indegree[node.id] += 1
                dependents[dep].append(node.id)

    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    ordered: list[Node] = []
    while ready:
        current = ready.pop(0)
        ordered.append(by_id[current])
        for child in dependents[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    if len(ordered) != len(nodes):
        remaining = sorted(set(by_id) - {node.id for node in ordered})
        raise Conflict(
            "dependency cycle detected in execution graph; "
            f"unresolved nodes: {', '.join(remaining)}"
        )
    return ordered


def manifest(dag: Dag, ticket: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce the execution manifest handed to the execution layer."""
    payload = {
        "task_id": dag.task_id,
        "objective": (ticket or {}).get("objective", ""),
        "acceptance": (ticket or {}).get("acceptance", ""),
        "scope": (ticket or {}).get("scope", []),
        "nodes": [node.to_dict() for node in dag.nodes],
        "next_node": next((node.id for node in dag.nodes if not node.done), None),
        "execution_authorized": False,
        "provenance": "derived from ticket structure; no execution has occurred",
    }
    payload["manifest_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return payload


def handoff_payload(
    dag: Dag,
    packet: dict[str, Any],
    ticket: dict[str, Any] | None = None,
    sandbox: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the full handoff: sandbox, manifest, and hydrated prompt."""
    return {
        "task_id": dag.task_id,
        "sandbox": sandbox or {},
        "manifest": manifest(dag, ticket),
        "packet": packet,
        "authorized": False,
        "note": "A handoff is prepared state, not permission to execute.",
    }


def parallel_groups(dag: Dag) -> list[list[str]]:
    """Group nodes into waves that could run in parallel."""
    done: set[str] = set()
    groups: list[list[str]] = []
    remaining = list(dag.nodes)
    while remaining:
        group = [
            node.id
            for node in remaining
            if all(dep in done or dep not in {n.id for n in remaining} for dep in node.depends_on)
        ]
        if not group:
            raise Conflict("dependency cycle detected while grouping parallel work")
        groups.append(group)
        done.update(group)
        remaining = [node for node in remaining if node.id not in done]
    return groups


def summarize(dag: Dag) -> dict[str, Any]:
    """Small summary used in status output."""
    return {
        "task_id": dag.task_id,
        "nodes": len(dag.nodes),
        "completed": sum(1 for node in dag.nodes if node.done),
        "files": sorted({path for node in dag.nodes for path in node.files}),
        "tests": sorted({path for node in dag.nodes for path in node.tests}),
        "parallel_groups": parallel_groups(dag),
    }
