from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from permitdiff.cli import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "validation/public-claude-permission-widening"
_ACK_FLAGS = [
    "--allow-ignored-root-changes",
    "--acknowledge-webfetch-sandbox-gap",
]


def test_claude_compare_writes_report_and_normalization_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    evidence_path = tmp_path / "claude-evidence.json"

    result = runner.invoke(
        app,
        [
            "claude",
            "compare",
            str(PILOT / "source-baseline.json"),
            str(PILOT / "source-candidate.json"),
            str(PILOT / "corpus.jsonl"),
            *_ACK_FLAGS,
            "--strict",
            "--format",
            "json",
            "--output",
            str(report_path),
            "--evidence-output",
            str(evidence_path),
        ],
    )

    assert result.exit_code == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert report["comparison"]["summary"]["privilege_expansions"] == 2
    assert report["comparison"]["summary"]["static_authority_unknowns"] == 0
    assert report["gate"]["passed"] is False
    assert evidence["adapter"] == "claude-code-project-preapprovals"
    assert evidence["candidate_redundant_allow_rules"] == ["Bash(git mv *)"]
    assert evidence["changed_ignored_root_keys"] == ["enabledPlugins"]
    assert evidence["ignored_root_changes_acknowledged"] is True
    assert evidence["webfetch_sandbox_gap_acknowledged"] is True


def test_claude_compare_json_stdout_is_machine_parseable() -> None:
    result = runner.invoke(
        app,
        [
            "claude",
            "compare",
            str(PILOT / "source-baseline.json"),
            str(PILOT / "source-candidate.json"),
            str(PILOT / "corpus.jsonl"),
            *_ACK_FLAGS,
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["comparison"]["summary"]["changed_effects"] == 2


def test_claude_compare_rejects_unacknowledged_root_drift() -> None:
    result = runner.invoke(
        app,
        [
            "claude",
            "compare",
            str(PILOT / "source-baseline.json"),
            str(PILOT / "source-candidate.json"),
            str(PILOT / "corpus.jsonl"),
        ],
    )

    assert result.exit_code == 1
    assert "non-permissions Claude root settings changed" in result.output


def test_claude_compare_requires_webfetch_gap_ack_after_root_ack() -> None:
    result = runner.invoke(
        app,
        [
            "claude",
            "compare",
            str(PILOT / "source-baseline.json"),
            str(PILOT / "source-candidate.json"),
            str(PILOT / "corpus.jsonl"),
            "--allow-ignored-root-changes",
        ],
    )

    assert result.exit_code == 1
    assert "explicit WebFetch sandbox-gap acknowledgement" in result.output


def test_claude_compare_rejects_non_dontask_mode(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    corpus = PILOT / "corpus.jsonl"
    settings = {"permissions": {"allow": [], "defaultMode": "default"}}
    baseline.write_text(json.dumps(settings), encoding="utf-8")
    candidate.write_text(json.dumps(settings), encoding="utf-8")

    result = runner.invoke(app, ["claude", "compare", str(baseline), str(candidate), str(corpus)])

    assert result.exit_code == 1
    assert "supports only explicit defaultMode='dontAsk'" in result.output
