"""Tests for execution DAG construction."""

from __future__ import annotations

import unittest

from el_hidratador.dag import (
    build_dag,
    handoff_payload,
    manifest,
    parallel_groups,
    parse_files,
    parse_tasks,
    parse_tests,
    summarize,
)
from el_hidratador.errors import Conflict, ValidationError

SAMPLE = """
## Description
Implement proper JWT-based authentication.

## Tasks
- [x] Design JWT token structure and claims
- [ ] Implement token issuance endpoint
- [ ] Add token validation middleware
- [ ] Implement refresh token rotation

## Files Created
- `auth/jwt.py` - JWT authentication utilities
- `auth/routes.py` - Route handlers
- `tests/test_jwt.py` - JWT test suite
"""


class ParseTests(unittest.TestCase):
    def test_tasks_are_parsed_with_completion_state(self) -> None:
        tasks = parse_tasks(SAMPLE)
        self.assertEqual(len(tasks), 4)
        self.assertTrue(tasks[0]["done"])
        self.assertFalse(tasks[1]["done"])

    def test_dependencies_are_extracted_from_task_text(self) -> None:
        tasks = parse_tasks("- [ ] Wire the adapter depends on M-1002\n")
        self.assertEqual(tasks[0]["depends_on"], ["M-1002"])

    def test_files_are_parsed_from_named_section(self) -> None:
        files = parse_files(SAMPLE)
        self.assertIn("auth/jwt.py", files)
        self.assertIn("auth/routes.py", files)

    def test_tests_fall_back_to_files_section(self) -> None:
        tests = parse_tests(SAMPLE)
        self.assertIn("tests/test_jwt.py", tests)

    def test_no_tasks_yields_no_nodes(self) -> None:
        self.assertEqual(parse_tasks(""), [])


class DagTests(unittest.TestCase):
    def test_dag_orders_nodes_deterministically(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        orders = [node.order for node in dag.nodes]
        self.assertEqual(orders, list(range(len(dag.nodes))))
        again = build_dag("M-1001", markdown=SAMPLE)
        self.assertEqual([n.to_dict() for n in dag.nodes], [n.to_dict() for n in again.nodes])

    def test_completed_tasks_are_marked(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        self.assertTrue(dag.nodes[0].done)
        self.assertFalse(dag.nodes[1].done)

    def test_empty_ticket_still_produces_one_node(self) -> None:
        dag = build_dag("M-1001")
        self.assertEqual(len(dag.nodes), 1)

    def test_ticket_dependencies_become_a_root_node(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE, ticket_dependencies=["M-0999"])
        self.assertEqual(dag.nodes[0].id, "M-1001:prerequisites")
        self.assertIn("M-0999", dag.nodes[0].depends_on)

    def test_cycle_is_refused(self) -> None:
        markdown = "- [ ] Step A depends on M-b\n- [ ] Step B depends on M-a\n"
        dag_nodes = []
        from el_hidratador.dag import Node

        dag_nodes = [
            Node(id="a", title="A", depends_on=["b"]),
            Node(id="b", title="B", depends_on=["a"]),
        ]
        from el_hidratador.dag import _topological_order

        with self.assertRaises(Conflict):
            _topological_order(dag_nodes)
        self.assertIsNotNone(dag_nodes)
        self.assertIsNotNone(markdown)

    def test_manifest_declares_no_execution(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        result = manifest(dag, {"objective": "o", "acceptance": "a"})
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["task_id"], "M-1001")
        self.assertEqual(len(result["manifest_hash"]), 16)

    def test_manifest_hash_is_stable(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        first = manifest(dag, {"objective": "o"})["manifest_hash"]
        second = manifest(build_dag("M-1001", markdown=SAMPLE), {"objective": "o"})["manifest_hash"]
        self.assertEqual(first, second)

    def test_next_node_points_at_incomplete_work(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        result = manifest(dag)
        self.assertEqual(result["next_node"], dag.nodes[1].id)

    def test_parallel_groups_cover_every_node(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        groups = parallel_groups(dag)
        flat = [node for group in groups for node in group]
        self.assertEqual(sorted(flat), sorted(node.id for node in dag.nodes))

    def test_summarize_reports_files_and_tests(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        summary = summarize(dag)
        self.assertGreater(summary["nodes"], 0)
        self.assertIn("auth/jwt.py", summary["files"])

    def test_handoff_payload_is_not_authorization(self) -> None:
        dag = build_dag("M-1001", markdown=SAMPLE)
        payload = handoff_payload(dag, {"packet": True}, {"objective": "o"}, {"image": "x"})
        self.assertFalse(payload["authorized"])
        self.assertIn("manifest", payload)
        self.assertIn("sandbox", payload)

    def test_invalid_task_id_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            build_dag("")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
