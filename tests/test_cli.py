from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from permitdiff import __version__
from permitdiff.cli import app

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_policy_validate_command() -> None:
    result = runner.invoke(app, ["policy", "validate", str(EXAMPLES / "baseline.yaml")])
    assert result.exit_code == 0
    assert "valid" in result.stdout
    assert "sha256:" in result.stdout


def test_corpus_validate_command() -> None:
    result = runner.invoke(app, ["corpus", "validate", str(EXAMPLES / "corpus.jsonl")])
    assert result.exit_code == 0
    assert "5 scenarios" in result.stdout


def test_compare_json_gate_failure_is_parseable() -> None:
    result = runner.invoke(
        app,
        [
            "compare",
            str(EXAMPLES / "baseline.yaml"),
            str(EXAMPLES / "candidate.yaml"),
            str(EXAMPLES / "corpus.jsonl"),
            "--gate",
            str(EXAMPLES / "gate.yaml"),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["gate"]["passed"] is False


def test_compare_writes_markdown_report(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "compare",
            str(EXAMPLES / "baseline.yaml"),
            str(EXAMPLES / "candidate.yaml"),
            str(EXAMPLES / "corpus.jsonl"),
            "--format",
            "markdown",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert output.read_text(encoding="utf-8").startswith("# PermitDiff report")


def test_compare_rejects_conflicting_gate_modes() -> None:
    result = runner.invoke(
        app,
        [
            "compare",
            str(EXAMPLES / "baseline.yaml"),
            str(EXAMPLES / "candidate.yaml"),
            str(EXAMPLES / "corpus.jsonl"),
            "--gate",
            str(EXAMPLES / "gate.yaml"),
            "--strict",
        ],
    )
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_init_creates_starter(tmp_path: Path) -> None:
    destination = tmp_path / "starter"
    result = runner.invoke(app, ["init", str(destination)])
    assert result.exit_code == 0
    assert (destination / "policies/baseline.yaml").exists()
    assert "Run: permitdiff compare" in result.stdout


def test_policy_show_command() -> None:
    result = runner.invoke(app, ["policy", "show", str(EXAMPLES / "candidate.yaml")])
    assert result.exit_code == 0
    assert "allow-low-value-refunds" in result.stdout
    assert "default: deny" in result.stdout


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "starter"
    assert runner.invoke(app, ["init", str(destination)]).exit_code == 0
    result = runner.invoke(app, ["init", str(destination)])
    assert result.exit_code == 1
    assert "refusing to overwrite" in result.output


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"permitdiff {__version__}"
