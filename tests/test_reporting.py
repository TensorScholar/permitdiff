from __future__ import annotations

import json
from pathlib import Path

from permitdiff.analysis import compare_policies
from permitdiff.gate import evaluate_gate, strict_gate
from permitdiff.models import Scenario
from permitdiff.policy import PolicyDocument
from permitdiff.reporting import ReportBundle


def _bundle(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> ReportBundle:
    report = compare_policies(baseline, candidate, scenarios)
    return ReportBundle(report, evaluate_gate(report, strict_gate()))


def test_json_report_is_machine_readable(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    payload = json.loads(_bundle(baseline, candidate, scenarios).json())
    assert payload["schema_version"] == "permitdiff.bundle/v1alpha1"
    assert payload["comparison"]["summary"]["privilege_expansions"] == 1
    assert payload["comparison"]["summary"]["static_authority_expansions"] == 1
    assert payload["comparison"]["authority_findings"][0]["code"] == "rule_added"
    assert payload["gate"]["passed"] is False


def test_markdown_contains_review_sections(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    markdown = _bundle(baseline, candidate, scenarios).markdown()
    assert "# PermitDiff report" in markdown
    assert "## Permission changes" in markdown
    assert "refund-50" in markdown
    assert "## Static authority analysis" in markdown
    assert "rule_added" in markdown
    assert "Observed scenario coverage is evidence" in markdown
    assert "## Gate" in markdown


def test_sarif_emits_observed_and_static_authority_results(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
    tmp_path: Path,
) -> None:
    payload = json.loads(_bundle(baseline, candidate, scenarios).sarif(tmp_path / "candidate.yaml"))
    results = payload["runs"][0]["results"]
    rule_ids = {item["ruleId"] for item in results}
    assert "permitdiff/privilege-expansion" in rule_ids
    assert "permitdiff/static-authority-expansion" in rule_ids
    assert all(item["locations"] for item in results)


def test_console_returns_text_without_writing_stdout(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
    capsys,
) -> None:
    rendered = _bundle(baseline, candidate, scenarios).console()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "PermitDiff:" in rendered
    assert "refund-50" in rendered
    assert "Static authority findings" in rendered


def test_json_report_omits_absent_gate(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    report = compare_policies(baseline, candidate, scenarios)
    payload = json.loads(ReportBundle(report).json())
    assert "gate" not in payload
