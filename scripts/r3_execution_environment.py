#!/usr/bin/env python3
"""Validate the exact R3 PermitDiff execution-environment identity."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class EnvironmentLockError(ValueError):
    """Raised when execution environment identity drifts from the frozen lock."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_lock(path: Path, schema_path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    if not isinstance(payload, dict):
        raise EnvironmentLockError("environment lock must be a JSON object")
    return payload


def _git_show(repo: Path, commit: str, path: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "show", f"{commit}:{path}"], stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as exc:
        raise EnvironmentLockError(
            f"cannot read frozen product artifact {commit}:{path}: "
            f"{exc.output.decode(errors='replace')}"
        ) from exc


def validate_source_artifacts(lock: dict[str, Any], repo: Path) -> None:
    """Verify product-commit provenance and the R3-specific dependency lock snapshots."""

    commit = str(lock["product_commit"])
    artifacts = lock["source_artifacts"]
    if not isinstance(artifacts, dict):
        raise EnvironmentLockError("source_artifacts must be an object")
    for name, raw in artifacts.items():
        if not isinstance(raw, dict):
            raise EnvironmentLockError(f"malformed source artifact: {name}")
        path = str(raw["path"])
        data = _git_show(repo, commit, path)
        expected_sha256 = raw.get("sha256")
        if expected_sha256 is not None and _sha256(data) != expected_sha256:
            raise EnvironmentLockError(f"{name} SHA-256 drift")
        expected_blob = str(raw["git_blob_sha"])
        actual_blob = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", f"{commit}:{path}"], text=True
        ).strip()
        if actual_blob != expected_blob:
            raise EnvironmentLockError(f"{name} Git blob drift")

    validate_dependency_lock_files(lock, repo)


def validate_dependency_lock_files(lock: dict[str, Any], repo: Path) -> None:
    """Verify the R3-specific dependency lock snapshots by content digest."""

    locks = lock["r3_dependency_locks"]
    if not isinstance(locks, dict):
        raise EnvironmentLockError("r3_dependency_locks must be an object")
    for role in ("runtime", "build"):
        entry = locks.get(role)
        if not isinstance(entry, dict):
            raise EnvironmentLockError(f"missing R3 {role} dependency lock")
        path = repo / str(entry["path"])
        try:
            actual = _sha256(path.read_bytes())
        except OSError as exc:
            raise EnvironmentLockError(f"cannot read R3 {role} dependency lock: {path}") from exc
        if actual != entry["sha256"]:
            raise EnvironmentLockError(f"R3 {role} dependency-lock digest drift")


def validate_environment_snapshot(lock: dict[str, Any], snapshot: dict[str, Any]) -> None:
    """Fail closed when a realized execution environment differs from the frozen identity."""

    if snapshot.get("python_version") != lock["python_version"]:
        raise EnvironmentLockError("Python version drift")
    expected_platform = lock["platform"]
    if snapshot.get("os") != expected_platform["os"]:
        raise EnvironmentLockError("OS drift")
    if snapshot.get("architecture") != expected_platform["architecture"]:
        raise EnvironmentLockError("architecture drift")
    if snapshot.get("timezone") != lock["execution"]["timezone"]:
        raise EnvironmentLockError("timezone drift")
    if str(snapshot.get("encoding", "")).upper().replace("-", "") != "UTF8":
        raise EnvironmentLockError("execution encoding is not UTF-8")
    installed = snapshot.get("packages")
    if not isinstance(installed, dict):
        raise EnvironmentLockError("package snapshot missing")
    expected = lock["runtime_dependencies"]
    for name, version in expected.items():
        observed = installed.get(name)
        if observed is None:
            observed = installed.get(name.lower())
        if observed != version:
            raise EnvironmentLockError(f"dependency drift for {name}: expected {version}")


def current_snapshot() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            packages[name] = dist.version
            packages[name.lower()] = dist.version
    machine = platform.machine().lower()
    if machine == "x86_64":
        machine = "amd64"
    return {
        "python_version": platform.python_version(),
        "os": platform.system().lower(),
        "architecture": machine,
        "timezone": os.environ.get("TZ", ""),
        "encoding": sys.getdefaultencoding(),
        "packages": packages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("docs/r3-execution-environment-lock.schema.json"),
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--validate-current", action="store_true")
    args = parser.parse_args()
    lock = load_lock(args.lock, args.schema)
    validate_source_artifacts(lock, args.repo)
    if args.validate_current:
        validate_environment_snapshot(lock, current_snapshot())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
