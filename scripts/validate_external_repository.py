#!/usr/bin/env python3
"""Verify a PermitDiff wheel by executing it from a pinned external repository checkout."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_EXPECTED_SUMMARY = {
    "privilege_expansions": 2,
    "new_allows": 2,
    "approval_bypasses": 0,
    "static_authority_expansions": 2,
    "static_authority_unknowns": 0,
}


def _run_git(*args: str, text: bool = True) -> subprocess.CompletedProcess[Any]:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode(errors="replace")
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return result


def _canonical_repository_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def _git_blob(ref: str, path: str) -> str:
    return str(_run_git("rev-parse", f"{ref}:{path}").stdout).strip()


def _git_show(ref: str, path: str) -> bytes:
    return bytes(_run_git("show", f"{ref}:{path}", text=False).stdout)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _installed_package_origin() -> Path:
    spec = importlib.util.find_spec("permitdiff")
    if spec is None or spec.origin is None:
        raise RuntimeError("installed permitdiff package cannot be located")
    return Path(spec.origin).resolve()


def _assert_external_checkout(
    *,
    expected_origin: str,
    baseline_commit: str,
    candidate_commit: str,
    source_path: str,
    baseline_blob: str,
    candidate_blob: str,
    evidence_root: Path,
) -> dict[str, str]:
    repository_root = Path(str(_run_git("rev-parse", "--show-toplevel").stdout).strip()).resolve()
    if Path.cwd().resolve() != repository_root:
        raise RuntimeError("validation must execute from the external repository root")

    actual_origin = str(_run_git("remote", "get-url", "origin").stdout).strip()
    if _canonical_repository_url(actual_origin) != _canonical_repository_url(expected_origin):
        raise RuntimeError(f"unexpected external repository origin: {actual_origin}")

    actual_head = str(_run_git("rev-parse", "HEAD").stdout).strip()
    if actual_head != candidate_commit:
        raise RuntimeError(f"unexpected external repository HEAD: {actual_head}")

    actual_baseline_blob = _git_blob(baseline_commit, source_path)
    actual_candidate_blob = _git_blob(candidate_commit, source_path)
    if actual_baseline_blob != baseline_blob:
        raise RuntimeError(f"baseline blob mismatch: {actual_baseline_blob}")
    if actual_candidate_blob != candidate_blob:
        raise RuntimeError(f"candidate blob mismatch: {actual_candidate_blob}")

    frozen_baseline = (evidence_root / "source-baseline.json").read_bytes()
    frozen_candidate = (evidence_root / "source-candidate.json").read_bytes()
    if _git_show(baseline_commit, source_path) != frozen_baseline:
        raise RuntimeError("frozen baseline evidence does not match the external repository blob")
    if (repository_root / source_path).read_bytes() != frozen_candidate:
        raise RuntimeError("frozen candidate evidence does not match the external repository checkout")

    return {
        "origin": actual_origin,
        "head": actual_head,
        "baseline_commit": baseline_commit,
        "source_path": source_path,
        "baseline_blob": actual_baseline_blob,
        "candidate_blob": actual_candidate_blob,
    }


def _run_permitdiff(evidence_root: Path) -> tuple[dict[str, Any], int]:
    command = [
        sys.executable,
        "-m",
        "permitdiff.cli",
        "compare",
        str((evidence_root / "baseline.yaml").resolve()),
        str((evidence_root / "candidate.yaml").resolve()),
        str((evidence_root / "corpus.jsonl").resolve()),
        "--gate",
        str((evidence_root / "gate.yaml").resolve()),
        "--format",
        "json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 2:
        raise RuntimeError(
            f"PermitDiff comparison returned {result.returncode}, expected intentional block 2\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"PermitDiff did not emit valid JSON: {exc}") from exc
    return payload, result.returncode


def _assert_report(payload: dict[str, Any]) -> dict[str, Any]:
    comparison = payload.get("comparison")
    gate = payload.get("gate")
    if not isinstance(comparison, dict) or not isinstance(gate, dict):
        raise RuntimeError("PermitDiff JSON is missing comparison or gate data")
    summary = comparison.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("PermitDiff JSON is missing comparison summary")
    for field, expected in _EXPECTED_SUMMARY.items():
        if summary.get(field) != expected:
            raise RuntimeError(f"unexpected {field}: {summary.get(field)!r}, expected {expected}")
    if gate.get("passed") is not False:
        raise RuntimeError("known permission widening was not blocked")
    candidate_coverage = comparison.get("candidate_coverage")
    if not isinstance(candidate_coverage, dict) or candidate_coverage.get("uncovered_rules") != []:
        raise RuntimeError("external validation candidate rules are not fully covered")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-origin", required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--baseline-blob", required=True)
    parser.add_argument("--candidate-blob", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence_root = args.evidence_root.resolve()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise RuntimeError(f"wheel does not exist: {wheel}")

    source_root = evidence_root.parents[1]
    package_origin = _installed_package_origin()
    if package_origin.is_relative_to(source_root):
        raise RuntimeError("PermitDiff resolved from the source checkout instead of the installed wheel")

    external = _assert_external_checkout(
        expected_origin=args.expected_origin,
        baseline_commit=args.baseline_commit,
        candidate_commit=args.candidate_commit,
        source_path=args.source_path,
        baseline_blob=args.baseline_blob,
        candidate_blob=args.candidate_blob,
        evidence_root=evidence_root,
    )
    payload, exit_code = _run_permitdiff(evidence_root)
    summary = _assert_report(payload)

    status = str(_run_git("status", "--porcelain").stdout)
    if status.strip():
        raise RuntimeError(f"external checkout was modified during validation:\n{status}")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema_version": "permitdiff.external-execution/v1alpha1",
        "external_repository": external,
        "release_candidate": {
            "version": importlib.metadata.version("permitdiff"),
            "wheel": wheel.name,
            "wheel_sha256": _sha256(wheel),
            "installed_from_wheel": True,
        },
        "execution": {
            "repository_root_cwd": True,
            "external_repository_code_executed": False,
            "cli_module": "permitdiff.cli",
            "exit_code": exit_code,
            "expected_gate_result": "block",
            "gate_passed": False,
            "summary": summary,
            "success": True,
        },
    }
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"external repository validation passed; evidence written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
