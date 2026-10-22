"""Tests for the file-backed ticket store and the JSON-first CLI."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from el_hidratador.cli import main
from el_hidratador.errors import ValidationError
from el_hidratador.tickets import TicketStore, parse_front_matter, render_ticket


class TicketStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TicketStore(Path(self.tmp.name) / ".hidratador")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ticket(self) -> dict:
        return {
            "id": "M-397001",
            "title": "Implement JWT authentication",
            "objective": "objective",
            "acceptance": "acceptance",
            "kind": "code",
            "status": "READY",
            "priority": 1,
            "scope": ["repo/api"],
            "tags": ["security"],
            "depends_on": [],
            "blocks": [],
            "owner": "terminal-1",
            "seed_key": "",
            "token_budget": 8000,
            "description": "body text",
            "acceptance_criteria": ["tokens work"],
            "created_at_iso": "2026-10-21T00:00:00.000Z",
            "updated_at_iso": "2026-10-21T00:00:00.000Z",
        }

    def test_ticket_round_trips_through_a_file(self) -> None:
        path = self.store.write_ticket(self._ticket())
        self.assertTrue(path.exists())
        meta = parse_front_matter(path.read_text(encoding="utf-8"))
        self.assertEqual(meta["id"], "M-397001")
        self.assertEqual(meta["status"], "READY")

    def test_index_is_rebuilt_from_files(self) -> None:
        self.store.write_ticket(self._ticket())
        index = json.loads(self.store.index_path.read_text(encoding="utf-8"))
        self.assertIn("M-397001", index)
        self.assertEqual(index["M-397001"]["status"], "READY")

    def test_list_tickets_reads_metadata(self) -> None:
        self.store.write_ticket(self._ticket())
        entries = self.store.list_tickets()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["id"], "M-397001")

    def test_evidence_is_written_per_task(self) -> None:
        path = self.store.write_evidence("M-397001", "checkpoint", {"tokens": 100})
        self.assertTrue(path.exists())
        records = self.store.evidence("M-397001")
        self.assertEqual(records[0]["tokens"], 100)

    def test_evidence_kinds_do_not_escape_the_directory(self) -> None:
        path = self.store.write_evidence("M-397001", "../../escape", {"x": 1})
        self.assertEqual(path.parent.name, "M-397001")

    def test_invalid_ticket_id_is_refused(self) -> None:
        with self.assertRaises(ValidationError):
            self.store.write_ticket({"id": "../evil"})

    def test_render_ticket_includes_acceptance_criteria(self) -> None:
        text = render_ticket(self._ticket())
        self.assertIn("## Acceptance Criteria", text)
        self.assertIn("- [ ] tokens work", text)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "ledger.sqlite")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *args: str) -> tuple[int, dict]:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["--db", self.db, *args])
        text = buffer.getvalue().strip()
        return code, json.loads(text) if text else {}

    def test_init_creates_a_ledger(self) -> None:
        code, payload = self._run("init")
        self.assertEqual(code, 0)
        self.assertTrue(payload["initialized"])

    def test_task_add_and_show_round_trip(self) -> None:
        code, _ = self._run(
            "task-add",
            "M-1001",
            "--objective",
            "do the work",
            "--acceptance",
            "the work is done",
            "--scope",
            "repo/api",
        )
        self.assertEqual(code, 0)
        code, payload = self._run("task-show", "M-1001")
        self.assertEqual(code, 0)
        self.assertEqual(payload["objective"], "do the work")

    def test_full_lifecycle_through_the_cli(self) -> None:
        self._run("task-add", "M-1001", "--objective", "o", "--acceptance", "a")
        code, payload = self._run("start", "M-1001", "--owner", "terminal-1")
        self.assertEqual(code, 0)
        session = payload["session_id"]
        code, payload = self._run(
            "checkpoint",
            session,
            "--summary",
            "s",
            "--evidence",
            "e",
            "--next",
            "n",
            "--tokens",
            "10",
        )
        self.assertEqual(code, 0)
        code, payload = self._run("finish", session, "--evidence", "all done")
        self.assertEqual(payload["status"], "REVIEW")
        code, payload = self._run("decide", "M-1001", "accept", "--reason", "reviewed")
        self.assertEqual(payload["status"], "DONE")

    def test_refused_operation_returns_exit_code_two(self) -> None:
        self._run("task-add", "M-1001", "--objective", "o", "--acceptance", "a")
        code, payload = self._run("decide", "M-1001", "accept", "--reason", "premature")
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])

    def test_pack_and_expand_emit_json(self) -> None:
        self._run("task-add", "M-1001", "--objective", "o", "--acceptance", "a")
        code, payload = self._run("pack", "M-1001")
        self.assertEqual(code, 0)
        self.assertIn("packet", payload)
        code, payload = self._run("expand", "M-1001")
        self.assertEqual(code, 0)
        self.assertIn("## Objective", payload["prompt"])

    def test_dag_command_builds_a_manifest(self) -> None:
        self._run("task-add", "M-1001", "--objective", "o", "--acceptance", "a")
        code, payload = self._run("dag", "M-1001")
        self.assertEqual(code, 0)
        self.assertFalse(payload["execution_authorized"])

    def test_export_writes_ticket_files(self) -> None:
        self._run("task-add", "M-1001", "--objective", "o", "--acceptance", "a")
        target = str(Path(self.tmp.name) / "exported")
        code, payload = self._run("export", "--dir", target)
        self.assertEqual(code, 0)
        self.assertTrue(Path(target, "tickets", "M-1001.md").exists())

    def test_status_and_events_are_json(self) -> None:
        code, payload = self._run("status")
        self.assertEqual(code, 0)
        self.assertIn("metrics", payload)
        code, payload = self._run("events")
        self.assertEqual(code, 0)
        self.assertIsInstance(payload["events"], list)

    def test_route_never_authorizes_execution(self) -> None:
        self._run("task-add", "M-1001", "--objective", "o", "--acceptance", "a")
        self._run(
            "profile-add",
            "local",
            "--kind",
            "code",
            "--context-limit",
            "16000",
            "--cost",
            "zero_incremental",
        )
        code, payload = self._run("route", "M-1001")
        self.assertEqual(code, 0)
        self.assertFalse(payload["execution_authorized"])

    def test_unknown_command_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            main(["--db", self.db, "not-a-command"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
