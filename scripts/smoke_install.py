#!/usr/bin/env python3
"""Smoke-test an installed distribution across release-facing CLI interfaces."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def run(
    *args: str,
    expected: int = 0,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "permitdiff.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"command failed ({result.returncode}, expected {expected}): {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def run_git(repository: Path, *args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git executable is required for installed-wheel smoke testing")
    result = subprocess.run(
        [str(Path(executable).resolve()), "-C", str(repository), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git command failed ({result.returncode}): {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def assert_installed_distribution() -> None:
    spec = importlib.util.find_spec("permitdiff")
    if spec is None or spec.origin is None:
        raise RuntimeError("installed permitdiff package cannot be located")
    package_origin = Path(spec.origin).resolve()
    if package_origin.is_relative_to(SOURCE_ROOT):
        raise RuntimeError(
            f"PermitDiff resolved from the source checkout instead of the installed wheel: "
            f"{package_origin}"
        )


def smoke_normalized_policy(root: Path) -> None:
    starter = root / "starter"
    run("init", str(starter))
    output = run(
        "compare",
        str(starter / "policies/baseline.yaml"),
        str(starter / "policies/candidate.yaml"),
        str(starter / "corpus.jsonl"),
        "--gate",
        str(starter / "permitdiff-gate.yaml"),
        "--format",
        "json",
        expected=2,
    )
    payload = json.loads(output.stdout)
    assert payload["comparison"]["summary"]["approval_bypasses"] == 1
    assert payload["gate"]["passed"] is False


def smoke_git_baseline(root: Path) -> None:
    repository = root / "git-baseline"
    run("init", str(repository))
    run_git(repository, "init")
    run_git(repository, "add", ".")
    run_git(
        repository,
        "-c",
        "user.name=PermitDiff Smoke",
        "-c",
        "user.email=smoke@permitdiff.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        "freeze baseline",
    )

    evidence_path = repository / "baseline-source.json"
    report_path = repository / "git-report.json"
    run(
        "compare",
        "policies/baseline.yaml",
        "policies/candidate.yaml",
        "corpus.jsonl",
        "--gate",
        "permitdiff-gate.yaml",
        "--baseline-ref",
        "HEAD",
        "--baseline-evidence-output",
        evidence_path.name,
        "--format",
        "json",
        "--output",
        report_path.name,
        expected=2,
        cwd=repository,
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    baseline_bytes = (repository / "policies/baseline.yaml").read_bytes()

    assert evidence["requested_ref"] == "HEAD"
    assert evidence["resolved_commit"] == run_git(repository, "rev-parse", "HEAD")
    assert evidence["git_object_id"] == run_git(
        repository,
        "rev-parse",
        "HEAD:policies/baseline.yaml",
    )
    assert evidence["raw_sha256"] == hashlib.sha256(baseline_bytes).hexdigest()
    assert report["gate"]["passed"] is False


def write_claude_corpus(path: Path) -> None:
    scenarios = [
        {
            "id": "existing-bash",
            "risk": "medium",
            "description": "Existing Bash preapproval remains unchanged.",
            "action": {
                "request_id": "wheel-bash",
                "principal": "project:developer",
                "agent": "claude-code",
                "tool": "Bash",
                "arguments": {"command": "git status"},
                "context": {
                    "environment": "smoke",
                    "source": "installed-wheel-smoke",
                    "security_metadata_trusted": False,
                },
            },
        },
        {
            "id": "new-websearch",
            "risk": "medium",
            "description": "Candidate newly preapproves WebSearch under dontAsk.",
            "action": {
                "request_id": "wheel-websearch",
                "principal": "project:developer",
                "agent": "claude-code",
                "tool": "WebSearch",
                "arguments": {"query": "permission documentation"},
                "context": {
                    "environment": "smoke",
                    "source": "installed-wheel-smoke",
                    "security_metadata_trusted": False,
                },
            },
        },
    ]
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in scenarios),
        encoding="utf-8",
    )


def smoke_claude_projection(root: Path) -> None:
    case = root / "claude"
    case.mkdir()
    baseline_path = case / "baseline.json"
    candidate_path = case / "candidate.json"
    corpus_path = case / "corpus.jsonl"
    report_path = case / "report.json"
    evidence_path = case / "evidence.json"

    baseline = {
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": ["Bash"],
            "ask": [],
            "deny": [],
        }
    }
    candidate = {
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": ["Bash", "WebSearch"],
            "ask": [],
            "deny": [],
        }
    }
    baseline_path.write_text(json.dumps(baseline, sort_keys=True), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
    write_claude_corpus(corpus_path)

    run(
        "claude",
        "compare",
        str(baseline_path),
        str(candidate_path),
        str(corpus_path),
        "--strict",
        "--format",
        "json",
        "--output",
        str(report_path),
        "--evidence-output",
        str(evidence_path),
        expected=2,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    summary = report["comparison"]["summary"]

    assert summary["privilege_expansions"] == 1
    assert summary["new_allows"] == 1
    assert summary["static_authority_expansions"] == 1
    assert summary["static_authority_unknowns"] == 0
    assert report["gate"]["passed"] is False
    assert evidence["adapter"] == "claude-code-project-preapprovals"
    assert evidence["changed_ignored_root_keys"] == []
    assert evidence["ignored_root_changes_acknowledged"] is False
    assert evidence["webfetch_sandbox_gap_acknowledged"] is False


def main() -> int:
    assert_installed_distribution()
    with tempfile.TemporaryDirectory(prefix="permitdiff-smoke-") as directory:
        root = Path(directory)
        smoke_normalized_policy(root)
        smoke_git_baseline(root)
        smoke_claude_projection(root)
    print("installed distribution public-interface smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
