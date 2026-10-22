"""Durable GitHub observations and a reconciled outbox.

Two halves, kept strictly apart:

* **Observations** are read-only. El Hidratador watches a repository and records
  what it saw. It never mutates GitHub state while observing.
* **The outbox** is the write path. Every write carries an idempotency key, a
  body hash, and a marker comment. Before sending, the adapter reconciles
  against what is already on the issue, so a repeated run never double-posts.

The adapter shells out to the `gh` CLI. No token is ever read, stored, or
passed through this module — `gh` owns authentication.

The `gh` CLI is the declared boundary of this adapter: the argv is fixed, the
executable is resolved with `shutil.which`, no shell is involved, and every
invocation has a timeout.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess  # nosec B404
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .errors import AdapterError, ValidationError

#: Seconds allowed for a single `gh` invocation.
GH_TIMEOUT = 30

#: Maximum bytes read back from a `gh` invocation.
GH_MAX_OUTPUT = 16 * 1024 * 1024

#: Observation kinds this adapter understands.
OBSERVATION_KINDS = (
    "issues",
    "comments",
    "pulls",
    "review_comments",
    "releases",
    "runs",
    "commits",
    "events",
)

#: Actions the observation layer can recommend.
ACTIONS = (
    "investigate_failed_check",
    "review_code_change",
    "reconcile_ticket_change",
    "review_external_feedback",
    "verify_release_artifacts",
    "inspect_repository_activity",
)


def body_hash(body: str) -> str:
    """SHA-256 of a message body."""
    return hashlib.sha256(body.encode()).hexdigest()


def marker(key: str, digest: str) -> str:
    """The idempotency marker appended to every published body."""
    return f"<!-- hidratador:{key}:{digest} -->"


def _validate_key(key: str) -> str:
    text = str(key or "").strip()
    if not text:
        raise ValidationError("outbox key must be nonempty")
    if len(text) > 100:
        raise ValidationError("outbox key must be 100 characters or fewer")
    if "\n" in text or "<!--" in text:
        raise ValidationError("outbox key must not contain newlines or comment markers")
    return text


def _validate_repo(repo: str) -> str:
    text = str(repo or "").strip()
    if text.count("/") != 1 or any(part == "" for part in text.split("/")):
        raise ValidationError("repo must be in owner/name form")
    return text


class GitHubSync:
    """Read-only observations plus a reconciled write outbox."""

    def __init__(
        self,
        db_path: Path | None = None,
        repo: str | None = None,
        timeout: int = GH_TIMEOUT,
    ) -> None:
        self.repo = _validate_repo(repo) if repo else None
        self.timeout = timeout
        self.db_path = Path(
            db_path or os.environ.get("HIDRATADOR_GITHUB_DB", "~/.el-hidratador/github.sqlite")
        ).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                repo TEXT NOT NULL,
                kind TEXT NOT NULL,
                identity TEXT NOT NULL,
                revision TEXT NOT NULL DEFAULT '',
                observed TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (repo, kind, identity)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                repo TEXT NOT NULL,
                issue INTEGER NOT NULL,
                key TEXT NOT NULL,
                body_hash TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT 'pending',
                url TEXT NOT NULL DEFAULT '',
                created REAL NOT NULL,
                PRIMARY KEY (repo, issue, key)
            );
            """
        )

    def close(self) -> None:
        with contextlib.suppress(sqlite3.Error):  # pragma: no cover - defensive
            self.db.close()

    # ------------------------------------------------------------------
    # gh adapter
    # ------------------------------------------------------------------
    def _gh(self, args: Sequence[str]) -> str:
        """Run a `gh` subcommand and return stdout."""
        if shutil.which("gh") is None:
            raise AdapterError("gh executable not found on PATH")
        try:
            completed = subprocess.run(  # nosec B603 B607
                ["gh", *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"gh {' '.join(args[:2])} timed out after {self.timeout}s") from exc
        if len(completed.stdout.encode()) > GH_MAX_OUTPUT:
            raise AdapterError("gh response exceeded the 16 MiB limit")
        if completed.returncode != 0:
            raise AdapterError(f"gh {args[0]} failed: {completed.stderr.strip()[:400]}")
        return completed.stdout

    def _gh_json(self, args: Sequence[str], fields: Sequence[str]) -> Any:
        raw = self._gh([*args, "--json", ",".join(fields)])
        try:
            return json.loads(raw or "null")
        except json.JSONDecodeError as exc:
            raise AdapterError("gh returned malformed JSON") from exc

    # ------------------------------------------------------------------
    # observations
    # ------------------------------------------------------------------
    def record_observation(
        self,
        repo: str,
        kind: str,
        identity: str,
        revision: str = "",
        observed: str = "",
        summary: str = "",
        action: str = "",
        url: str = "",
    ) -> dict[str, Any]:
        """Persist one observation. Read-only with respect to GitHub."""
        repo_name = _validate_repo(repo)
        if kind not in OBSERVATION_KINDS:
            raise ValidationError(f"unknown observation kind: {kind}")
        if action and action not in ACTIONS:
            raise ValidationError(f"unknown observation action: {action}")
        self.db.execute(
            "INSERT INTO observations(repo,kind,identity,revision,observed,summary,action,url) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(repo,kind,identity) DO UPDATE SET "
            "revision=excluded.revision, observed=excluded.observed, summary=excluded.summary, "
            "action=excluded.action, url=excluded.url",
            (repo_name, kind, str(identity), revision, observed, summary, action, url),
        )
        return {
            "repo": repo_name,
            "kind": kind,
            "identity": str(identity),
            "revision": revision,
            "observed": observed,
            "summary": summary,
            "action": action,
            "url": url,
        }

    def observations(
        self, repo: str | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if repo:
            clauses.append("repo=?")
            params.append(_validate_repo(repo))
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        # The clause list is built from fixed fragments and every value is
        # bound as a parameter, so no caller input reaches the statement text.
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.db.execute(
            f"SELECT * FROM observations{where} ORDER BY repo, kind, identity",  # nosec B608
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def poll(self, repo: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        """Observe a repository and record what changed.

        ``dry_run`` (the default) collects observations without persisting them,
        so a caller can review before writing to the observation store.
        """
        repo_name = _validate_repo(repo or self.repo or "")
        if not repo_name:
            raise ValidationError("a repo is required for polling")
        collected: list[dict[str, Any]] = []

        issues = self._gh_json(
            ["issue", "list", "--repo", repo_name, "--limit", "100"],
            ["number", "title", "state", "url", "labels", "updatedAt"],
        )
        for issue in issues or []:
            number = issue.get("number")
            labels = [label.get("name", "") for label in issue.get("labels") or []]
            action = "reconcile_ticket_change" if "needs-triage" in labels else ""
            collected.append(
                {
                    "kind": "issues",
                    "identity": f"#{number}",
                    "revision": issue.get("updatedAt", ""),
                    "observed": issue.get("state", ""),
                    "summary": issue.get("title", ""),
                    "action": action,
                    "url": issue.get("url", ""),
                }
            )
            comments = self._gh_json(
                ["issue", "view", str(number), "--repo", repo_name, "--json", "comments"],
                ["comments"],
            )
            for comment in (comments or {}).get("comments", []) or []:
                author = comment.get("author")
                collected.append(
                    {
                        "kind": "comments",
                        "identity": f"#{number}",
                        "revision": comment.get("createdAt", "") or comment.get("updatedAt", ""),
                        "observed": author.get("login", "") if isinstance(author, dict) else "",
                        "summary": (comment.get("body", "") or "")[:280],
                        "action": "review_external_feedback",
                        "url": issue.get("url", ""),
                    }
                )

        pulls = self._gh_json(
            ["pr", "list", "--repo", repo_name, "--limit", "100"],
            ["number", "title", "state", "url", "updatedAt"],
        )
        for pull in pulls or []:
            collected.append(
                {
                    "kind": "pulls",
                    "identity": f"#{pull.get('number')}",
                    "revision": pull.get("updatedAt", ""),
                    "observed": pull.get("state", ""),
                    "summary": pull.get("title", ""),
                    "action": "review_code_change",
                    "url": pull.get("url", ""),
                }
            )

        releases = self._gh_json(
            ["release", "list", "--repo", repo_name, "--limit", "50"],
            ["tagName", "name", "isDraft", "publishedAt", "url"],
        )
        for release in releases or []:
            collected.append(
                {
                    "kind": "releases",
                    "identity": str(release.get("tagName", "")),
                    "revision": release.get("publishedAt", ""),
                    "observed": "draft" if release.get("isDraft") else "published",
                    "summary": release.get("name", "") or release.get("tagName", ""),
                    "action": "verify_release_artifacts",
                    "url": release.get("url", ""),
                }
            )

        if dry_run:
            return {"repo": repo_name, "dry_run": True, "observations": collected}

        for item in collected:
            self.record_observation(repo=repo_name, **item)
        return {"repo": repo_name, "dry_run": False, "observations": collected}

    # ------------------------------------------------------------------
    # outbox
    # ------------------------------------------------------------------
    def enqueue(self, repo: str, issue: int, key: str, body: str) -> dict[str, Any]:
        """Queue a message for publication. Idempotent per (repo, issue, key)."""
        repo_name = _validate_repo(repo)
        idempotency_key = _validate_key(key)
        if not isinstance(issue, int) or issue <= 0:
            raise ValidationError("issue must be a positive integer number")
        if not str(body or "").strip():
            raise ValidationError("body must be nonempty text")
        digest = body_hash(body)
        existing = self.db.execute(
            "SELECT * FROM outbox WHERE repo=? AND issue=? AND key=?",
            (repo_name, issue, idempotency_key),
        ).fetchone()
        if existing:
            if existing["body_hash"] != digest:
                raise ValidationError(
                    "outbox key already used with a different body; use a new key or reconcile manually"
                )
            return {**dict(existing), "created": False}
        self.db.execute(
            "INSERT INTO outbox(repo,issue,key,body_hash,body,state,url,created) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (repo_name, issue, idempotency_key, digest, body, "pending", "", time.time()),
        )
        return {
            "repo": repo_name,
            "issue": issue,
            "key": idempotency_key,
            "body_hash": digest,
            "state": "pending",
            "created": True,
        }

    def pending(self, repo: str | None = None) -> list[dict[str, Any]]:
        if repo:
            rows = self.db.execute(
                "SELECT * FROM outbox WHERE repo=? AND state='pending' ORDER BY created",
                (_validate_repo(repo),),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM outbox WHERE state='pending' ORDER BY created"
            ).fetchall()
        return [dict(row) for row in rows]

    def outbox(self, repo: str | None = None) -> list[dict[str, Any]]:
        if repo:
            rows = self.db.execute(
                "SELECT * FROM outbox WHERE repo=? ORDER BY created", (_validate_repo(repo),)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM outbox ORDER BY created").fetchall()
        return [dict(row) for row in rows]

    def publish(self, repo: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        """Publish pending outbox entries, reconciling before every send.

        Before posting, the adapter reads the issue's existing comments. If the
        marker is already present the entry is marked ``reconciled`` instead of
        being sent again.
        """
        repo_name = _validate_repo(repo or self.repo or "")
        results: list[dict[str, Any]] = []
        for entry in self.pending(repo_name or None):
            key = entry["key"]
            digest = entry["body_hash"]
            found = self._find_marker(repo_name, int(entry["issue"]), key, digest)
            if found is not None:
                self.db.execute(
                    "UPDATE outbox SET state='reconciled', url=? WHERE repo=? AND issue=? AND key=?",
                    (found, repo_name, entry["issue"], key),
                )
                results.append(
                    {
                        "key": key,
                        "issue": entry["issue"],
                        "action": "reconciled",
                        "url": found,
                        "note": "marker already present; nothing was sent",
                    }
                )
                continue
            if dry_run:
                results.append(
                    {
                        "key": key,
                        "issue": entry["issue"],
                        "action": "would_publish",
                        "note": "dry run; no comment was written",
                    }
                )
                continue
            body = f"{entry['body']}\n\n{marker(key, digest)}"
            output = self._gh(
                ["issue", "comment", str(entry["issue"]), "--repo", repo_name, "--body", body]
            )
            url = output.strip().splitlines()[-1] if output.strip() else ""
            self.db.execute(
                "UPDATE outbox SET state='published', url=? WHERE repo=? AND issue=? AND key=?",
                (url, repo_name, entry["issue"], key),
            )
            results.append({"key": key, "issue": entry["issue"], "action": "published", "url": url})
        return {"repo": repo_name, "dry_run": dry_run, "results": results}

    def _find_marker(self, repo: str, issue: int, key: str, digest: str) -> str | None:
        """Return the URL of an existing comment carrying the marker, if any."""
        target = marker(key, digest)
        try:
            payload = self._gh_json(
                ["issue", "view", str(issue), "--repo", repo, "--json", "comments,url"],
                ["comments", "url"],
            )
        except AdapterError:
            return None
        comments = (payload or {}).get("comments") or []
        for comment in comments:
            if target in (comment.get("body") or ""):
                url = (payload or {}).get("url", "")
                return str(url) if url else None
        return None

    def status(self, repo: str | None = None) -> dict[str, Any]:
        """Counts of observations and outbox states."""
        repo_name = _validate_repo(repo) if repo else None
        if repo_name:
            observations = self.observations(repo_name)
            outbox = self.outbox(repo_name)
        else:
            observations = self.observations()
            outbox = self.outbox()
        counts: dict[str, int] = {}
        for entry in outbox:
            counts[entry["state"]] = counts.get(entry["state"], 0) + 1
        return {
            "repo": repo_name,
            "observations": len(observations),
            "actions": sorted({item["action"] for item in observations if item["action"]}),
            "outbox": counts,
        }
