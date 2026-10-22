"""Tests for the adapters: sandbox, hardware router, GitHub sync, dashboard."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from el_hidratador.dashboard import ALLOWED_HOSTS, health, preview, validate_url
from el_hidratador.errors import AdapterError, ValidationError
from el_hidratador.github_sync import GitHubSync, body_hash, marker
from el_hidratador.hardware_router import (
    CLASS_HEAVY,
    CLASS_LIGHT,
    Target,
    classify,
    default_targets,
    dispatch_plan,
    evaluate,
    local_topology,
)
from el_hidratador.sandbox import (
    apply_sandbox,
    boundary_report,
    build_sandbox,
    docker_command,
)


class SandboxTests(unittest.TestCase):
    def test_sandbox_is_read_only_by_default(self) -> None:
        spec = build_sandbox("M-1", "/tmp/work")
        self.assertTrue(spec["read_only_root"])
        self.assertEqual(spec["network"], "none")
        self.assertFalse(spec["created"])

    def test_workspace_is_writable_and_repo_is_read_only(self) -> None:
        spec = build_sandbox("M-1", "/tmp/work", repo_mount="/tmp/repo")
        modes = {mount["target"]: mount["mode"] for mount in spec["mounts"]}
        self.assertEqual(modes["/workspace"], "rw")
        self.assertEqual(modes["/repo"], "ro")

    def test_relative_paths_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            build_sandbox("M-1", "relative/path")

    def test_invalid_environment_names_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            build_sandbox("M-1", "/tmp/work", environment={"BAD NAME": "x"})

    def test_spec_hash_is_stable(self) -> None:
        first = build_sandbox("M-1", "/tmp/work")["spec_hash"]
        second = build_sandbox("M-1", "/tmp/work")["spec_hash"]
        self.assertEqual(first, second)

    def test_docker_command_locks_the_boundary(self) -> None:
        spec = build_sandbox("M-1", "/tmp/work")
        argv = docker_command(spec)
        self.assertIn("--read-only", argv)
        self.assertIn("--network", argv)
        self.assertIn("no-new-privileges:true", argv)
        self.assertIn("--cap-drop", argv)

    def test_apply_defaults_to_dry_run(self) -> None:
        spec = build_sandbox("M-1", "/tmp/work")
        result = apply_sandbox(spec)
        self.assertFalse(result["applied"])
        self.assertTrue(result["dry_run"])

    def test_boundary_report_lists_paths(self) -> None:
        report = boundary_report(build_sandbox("M-1", "/tmp/work"))
        self.assertIn("/workspace", report["writable_paths"])
        self.assertEqual(report["network"], "none")


class HardwareRouterTests(unittest.TestCase):
    def test_heavy_kinds_route_to_heavy_class(self) -> None:
        self.assertEqual(classify({"kind": "planning"}), CLASS_HEAVY)

    def test_large_context_routes_to_heavy_class(self) -> None:
        self.assertEqual(classify({"kind": "code"}, 64_000), CLASS_HEAVY)

    def test_small_workload_routes_to_light_class(self) -> None:
        self.assertEqual(classify({"kind": "code"}, 100), CLASS_LIGHT)

    def test_paid_target_is_never_eligible(self) -> None:
        target = Target(id="cloud", class_name=CLASS_LIGHT, cost="paid", kinds=["code"])
        result = evaluate({"id": "M-1", "kind": "code"}, [target], 1024)
        self.assertFalse(result.options[0]["eligible"])
        self.assertFalse(result.execution_authorized)

    def test_unhealthy_target_is_never_eligible(self) -> None:
        target = Target(
            id="node",
            class_name=CLASS_LIGHT,
            cost="zero_incremental",
            kinds=["code"],
            healthy=False,
        )
        result = evaluate({"id": "M-1", "kind": "code"}, [target], 1024)
        self.assertFalse(result.options[0]["eligible"])

    def test_matching_target_is_eligible_but_not_authorized(self) -> None:
        target = Target(id="node", class_name=CLASS_LIGHT, cost="zero_incremental", kinds=["code"])
        result = evaluate({"id": "M-1", "kind": "code"}, [target], 1024)
        self.assertTrue(result.options[0]["eligible"])
        self.assertFalse(result.execution_authorized)

    def test_plan_never_authorizes_execution(self) -> None:
        target = Target(id="node", class_name=CLASS_LIGHT, cost="zero_incremental", kinds=["code"])
        result = evaluate({"id": "M-1", "kind": "code"}, [target], 1024)
        plan = dispatch_plan(result, "M-1")
        self.assertFalse(plan["execution_authorized"])
        self.assertTrue(plan["dry_run"])

    def test_default_targets_are_all_local_and_free(self) -> None:
        for target in default_targets():
            self.assertEqual(target.cost, "zero_incremental")

    def test_local_topology_reports_facts(self) -> None:
        topology = local_topology()
        self.assertIn("platform", topology)
        self.assertIn("python", topology)

    def test_invalid_required_context_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate({"id": "M-1"}, [], 0)


class GitHubSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.sync = GitHubSync(Path(self.tmp.name) / "github.sqlite")

    def tearDown(self) -> None:
        self.sync.close()
        self.tmp.cleanup()

    def test_repo_must_be_owner_name(self) -> None:
        with self.assertRaises(ValidationError):
            GitHubSync(repo="not-a-repo")

    def test_observation_requires_known_kind(self) -> None:
        with self.assertRaises(ValidationError):
            self.sync.record_observation("o/n", "invented", "1")

    def test_observations_are_recorded_and_read_back(self) -> None:
        self.sync.record_observation(
            "o/n",
            "issues",
            "#1",
            revision="v1",
            observed="open",
            summary="t",
            action="review_code_change",
        )
        found = self.sync.observations("o/n")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["action"], "review_code_change")

    def test_outbox_enqueue_is_idempotent(self) -> None:
        first = self.sync.enqueue("o/n", 7, "key-1", "body")
        second = self.sync.enqueue("o/n", 7, "key-1", "body")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(len(self.sync.pending("o/n")), 1)

    def test_outbox_key_reuse_with_different_body_is_refused(self) -> None:
        self.sync.enqueue("o/n", 7, "key-1", "body")
        with self.assertRaises(ValidationError):
            self.sync.enqueue("o/n", 7, "key-1", "different body")

    def test_outbox_key_is_length_limited(self) -> None:
        with self.assertRaises(ValidationError):
            self.sync.enqueue("o/n", 7, "k" * 101, "body")

    def test_issue_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            self.sync.enqueue("o/n", 0, "key", "body")

    def test_publish_dry_run_sends_nothing(self) -> None:
        self.sync.enqueue("o/n", 7, "key-1", "body")
        result = self.sync.publish("o/n", dry_run=True)
        self.assertEqual(result["results"][0]["action"], "would_publish")
        self.assertEqual(len(self.sync.pending("o/n")), 1)

    def test_existing_marker_reconciles_instead_of_resending(self) -> None:
        body = "hello"
        digest = body_hash(body)
        self.sync.enqueue("o/n", 7, "key-1", body)
        self.sync._gh_json = lambda *args, **kwargs: {  # type: ignore[method-assign]
            "url": "https://example.invalid/issue/7",
            "comments": [{"body": f"{body}\n\n{marker('key-1', digest)}"}],
        }
        result = self.sync.publish("o/n", dry_run=True)
        self.assertEqual(result["results"][0]["action"], "reconciled")
        self.assertEqual(self.sync.pending("o/n"), [])

    def test_publish_writes_once_and_records_state(self) -> None:
        self.sync.enqueue("o/n", 7, "key-1", "body")
        self.sync._gh_json = lambda *args, **kwargs: {"url": "", "comments": []}  # type: ignore[method-assign]
        calls: list[list[str]] = []
        self.sync._gh = lambda args: calls.append(list(args)) or "https://example.invalid/comment"  # type: ignore[method-assign]
        result = self.sync.publish("o/n", dry_run=False)
        self.assertEqual(result["results"][0]["action"], "published")
        self.assertEqual(len(calls), 1)
        self.assertIn("hidratador:key-1:", calls[0][-1])
        self.assertEqual(self.sync.pending("o/n"), [])

    def test_status_counts_outbox_states(self) -> None:
        self.sync.enqueue("o/n", 7, "key-1", "body")
        status = self.sync.status("o/n")
        self.assertEqual(status["outbox"]["pending"], 1)


class DashboardTests(unittest.TestCase):
    def test_loopback_urls_are_accepted(self) -> None:
        for host in ("localhost", "127.0.0.1"):
            self.assertTrue(validate_url(f"http://{host}:8080/dashboard"))

    def test_remote_hosts_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            validate_url("http://example.com/dashboard")

    def test_https_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            validate_url("https://127.0.0.1/dashboard")

    def test_credentials_in_url_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            validate_url("http://user:pass@127.0.0.1/dashboard")

    def test_empty_url_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            validate_url("")

    def test_allowed_hosts_are_loopback_only(self) -> None:
        for host in ALLOWED_HOSTS:
            self.assertTrue(
                host.startswith("127.")
                or host.startswith("::1")
                or host.startswith("[::1]")
                or host == "localhost"
            )

    def test_health_reports_unreachable_dashboard(self) -> None:
        result = health("http://127.0.0.1:9/never")
        self.assertFalse(result["reachable"])

    def test_preview_rejects_invalid_offsets(self) -> None:
        with self.assertRaises(ValidationError):
            preview("http://127.0.0.1:9/x", offset=-1)
        with self.assertRaises(ValidationError):
            preview("http://127.0.0.1:9/x", limit=0)

    def test_adapter_error_is_a_typed_error(self) -> None:
        self.assertTrue(issubclass(AdapterError, Exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
