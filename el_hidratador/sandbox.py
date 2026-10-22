"""Sandbox staging.

Taskrivet must land in a prepared, isolated workspace. This module builds the
sandbox *specification* — image, mounts, permissions, limits — as pure data,
so the specification can be reviewed, hashed, and diffed before anything is
created.

The optional adapter (`apply_sandbox`) shells out to the Docker CLI. It is
never invoked implicitly, it always has a timeout, and it never inherits a
credential environment by default.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .errors import AdapterError, ValidationError

#: Default container image used for staging sandboxes.
DEFAULT_IMAGE = "python:3.12-slim"

#: Hard ceiling for a staging container.
DEFAULT_MEMORY_LIMIT = "4g"
DEFAULT_CPU_LIMIT = "2.0"
DEFAULT_PIDS_LIMIT = 512


def _safe_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValidationError(f"sandbox path must be absolute: {path}")
    return candidate


def build_sandbox(
    task_id: str,
    workdir: str,
    image: str = DEFAULT_IMAGE,
    repo_mount: str | None = None,
    evidence_dir: str | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    cpu_limit: str = DEFAULT_CPU_LIMIT,
    pids_limit: int = DEFAULT_PIDS_LIMIT,
    network: str = "none",
    environment: dict[str, str] | None = None,
    read_only_root: bool = True,
) -> dict[str, Any]:
    """Build a sandbox specification. Pure function; creates nothing."""
    if not task_id:
        raise ValidationError("task_id must be nonempty")
    work = _safe_path(workdir)
    mounts: list[dict[str, Any]] = [
        {"source": str(work), "target": "/workspace", "mode": "rw", "purpose": "working tree"}
    ]
    if repo_mount:
        repo = _safe_path(repo_mount)
        mounts.append(
            {"source": str(repo), "target": "/repo", "mode": "ro", "purpose": "reference checkout"}
        )
    if evidence_dir:
        evidence = _safe_path(evidence_dir)
        mounts.append(
            {
                "source": str(evidence),
                "target": "/evidence",
                "mode": "ro",
                "purpose": "immutable log",
            }
        )
    env = {"PYTHONUNBUFFERED": "1", "HIDRATADOR_TASK_ID": task_id}
    for key, value in (environment or {}).items():
        if not key.replace("_", "").isalnum():
            raise ValidationError(f"invalid environment variable name: {key}")
        env[key] = str(value)

    spec: dict[str, Any] = {
        "task_id": task_id,
        "image": image,
        "workdir": str(work),
        "mounts": mounts,
        "read_only_root": read_only_root,
        "network": network,
        "resources": {
            "memory": memory_limit,
            "cpus": cpu_limit,
            "pids": pids_limit,
        },
        "environment": env,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "command": ["sleep", "infinity"],
        "created": False,
        "provenance": "declared staging boundary; not a running container",
    }
    spec["spec_hash"] = _hash(spec)
    return spec


def _hash(spec: dict[str, Any]) -> str:
    import hashlib

    payload = {key: value for key, value in spec.items() if key != "spec_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[
        :16
    ]


def docker_command(spec: dict[str, Any], name: str | None = None) -> list[str]:
    """Render the ``docker run`` argv for a sandbox specification."""
    container = name or f"hidratador-{spec['task_id'].lower()}"
    argv: list[str] = ["docker", "run", "-d", "--name", container]
    if spec.get("read_only_root"):
        argv.append("--read-only")
    if spec.get("network") == "none":
        argv += ["--network", "none"]
    for mount in spec.get("mounts", []):
        mode = "ro" if mount.get("mode") == "ro" else "rw"
        argv += ["--mount", f"type=bind,source={mount['source']},target={mount['target']},{mode}"]
    resources = spec.get("resources", {})
    if resources.get("memory"):
        argv += ["--memory", str(resources["memory"])]
    if resources.get("cpus"):
        argv += ["--cpus", str(resources["cpus"])]
    if resources.get("pids"):
        argv += ["--pids-limit", str(resources["pids"])]
    for capability in spec.get("cap_drop", []):
        argv += ["--cap-drop", capability]
    for option in spec.get("security_opt", []):
        argv += ["--security-opt", option]
    for key, value in spec.get("environment", {}).items():
        argv += ["-e", f"{key}={value}"]
    argv += [spec.get("image", DEFAULT_IMAGE)]
    argv += list(spec.get("command", []))
    return argv


def apply_sandbox(spec: dict[str, Any], timeout: int = 60, dry_run: bool = True) -> dict[str, Any]:
    """Create the container described by ``spec``.

    Defaults to a dry run so that staging is always an explicit action.
    """
    argv = docker_command(spec)
    if dry_run:
        return {
            "applied": False,
            "dry_run": True,
            "command": argv,
            "spec_hash": spec.get("spec_hash"),
        }
    if shutil.which("docker") is None:
        raise AdapterError("docker executable not found on PATH")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": os.environ.get("HOME", ""),
            },
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(f"docker run timed out after {timeout}s") from exc
    if completed.returncode != 0:
        raise AdapterError(f"docker run failed: {completed.stderr.strip()[:400]}")
    result = dict(spec)
    result["created"] = True
    result["container_id"] = completed.stdout.strip()[:64]
    result["spec_hash"] = spec.get("spec_hash")
    return result


def teardown_sandbox(name: str, timeout: int = 30) -> dict[str, Any]:
    """Remove a staging container. Never removes anything else."""
    if shutil.which("docker") is None:
        raise AdapterError("docker executable not found on PATH")
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(f"docker rm timed out after {timeout}s") from exc
    return {
        "removed": completed.returncode == 0,
        "container": name,
        "stderr": completed.stderr.strip()[:400],
    }


def boundary_report(spec: dict[str, Any]) -> dict[str, Any]:
    """Explain what the sandbox permits and forbids."""
    writable = [m["target"] for m in spec.get("mounts", []) if m.get("mode") == "rw"]
    readonly = [m["target"] for m in spec.get("mounts", []) if m.get("mode") == "ro"]
    return {
        "writable_paths": writable,
        "read_only_paths": readonly,
        "network": spec.get("network", "none"),
        "root_filesystem": "read-only" if spec.get("read_only_root") else "writable",
        "capabilities_dropped": spec.get("cap_drop", []),
        "note": "Scope enforcement is a container boundary, not an application check.",
    }
