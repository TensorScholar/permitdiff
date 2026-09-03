from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from permitdiff.cli import app
from permitdiff.errors import PolicyLoadError
from permitdiff.git_policy import load_policy_from_git
from permitdiff.policy import PolicyDocument

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_BASELINE = Path("examples/baseline.yaml")
EXAMPLE_CANDIDATE = Path("examples/candidate.yaml")
EXAMPLE_CORPUS = Path("examples/corpus.jsonl")
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
runner = CliRunner()


def test_git_policy_matches_worktree_policy_and_binds_source() -> None:
    resolved = load_policy_from_git("HEAD", EXAMPLE_BASELINE, repository=ROOT)
    local = PolicyDocument.from_yaml(ROOT / EXAMPLE_BASELINE)
    raw = (ROOT / EXAMPLE_BASELINE).read_bytes()

    assert resolved.policy == local
    assert resolved.evidence.requested_ref == "HEAD"
    assert resolved.evidence.path == EXAMPLE_BASELINE.as_posix()
    assert len(resolved.evidence.resolved_commit) in {40, 64}
    assert len(resolved.evidence.git_object_id) in {40, 64}
    assert resolved.evidence.raw_sha256 == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "ref",
    [" HEAD", "HEAD ", "-main", "HEAD~1", "main..candidate", "refs/heads/main@{1}"],
)
def test_git_policy_rejects_ambiguous_or_noncanonical_refs(ref: str) -> None:
    with pytest.raises(PolicyLoadError, match=r"Git baseline ref|unsupported Git"):
        load_policy_from_git(ref, EXAMPLE_BASELINE, repository=ROOT)


@pytest.mark.parametrize(
    "path",
    ["../examples/baseline.yaml", "/examples/baseline.yaml", "examples\\baseline.yaml"],
)
def test_git_policy_rejects_noncanonical_paths(path: str) -> None:
    with pytest.raises(PolicyLoadError, match="Git policy path"):
        load_policy_from_git("HEAD", path, repository=ROOT)


def test_git_policy_rejects_missing_blob() -> None:
    with pytest.raises(PolicyLoadError, match="git rev-parse"):
        load_policy_from_git("HEAD", "examples/does-not-exist.yaml", repository=ROOT)


def test_git_policy_rejects_non_repository_directory(tmp_path: Path) -> None:
    with pytest.raises(PolicyLoadError, match="git rev-parse"):
        load_policy_from_git("HEAD", EXAMPLE_BASELINE, repository=tmp_path)


def test_compare_can_resolve_baseline_from_git_and_write_provenance(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    evidence_path = tmp_path / "baseline-source.json"

    result = runner.invoke(
        app,
        [
            "compare",
            str(EXAMPLE_BASELINE),
            str(EXAMPLE_CANDIDATE),
            str(EXAMPLE_CORPUS),
            "--baseline-ref",
            "HEAD",
            "--baseline-evidence-output",
            str(evidence_path),
            "--format",
            "json",
            "--output",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    local_baseline = PolicyDocument.from_yaml(ROOT / EXAMPLE_BASELINE)

    assert report["comparison"]["baseline_digest"] == local_baseline.digest()
    assert evidence["schema_version"] == "permitdiff.git-policy-source/v1alpha1"
    assert evidence["requested_ref"] == "HEAD"
    assert evidence["path"] == EXAMPLE_BASELINE.as_posix()
    assert len(evidence["resolved_commit"]) in {40, 64}


def test_baseline_evidence_output_requires_git_ref(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "compare",
            str(EXAMPLE_BASELINE),
            str(EXAMPLE_CANDIDATE),
            str(EXAMPLE_CORPUS),
            "--baseline-evidence-output",
            str(tmp_path / "evidence.json"),
        ],
    )

    assert result.exit_code == 2
    output = _ANSI_ESCAPE.sub("", result.output)
    assert "--baseline-evidence-output requires --baseline-ref" in output
