"""Human-readable and CI-native report rendering."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

from permitdiff._version import __version__
from permitdiff.analysis import ComparisonReport, ScenarioTransition
from permitdiff.authority import AuthorityFinding, AuthorityFindingKind
from permitdiff.gate import GateResult


class ReportEnvelope(BaseModel):
    """Versioned JSON envelope for one comparison and optional gate result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "permitdiff.bundle/v1alpha1"
    comparison: ComparisonReport
    gate: GateResult | None = None


class ReportBundle:
    """Render one comparison and optional gate result into supported formats."""

    def __init__(self, report: ComparisonReport, gate: GateResult | None = None) -> None:
        self.report = report
        self.gate = gate

    def json(self) -> str:
        payload = ReportEnvelope(comparison=self.report, gate=self.gate)
        return (
            json.dumps(
                payload.model_dump(mode="json", exclude_none=True),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        )

    def markdown(self) -> str:
        report = self.report
        verdict = _verdict(self.gate)
        lines = [
            "# PermitDiff report",
            "",
            f"**Verdict:** {verdict}",
            "",
            f"- Baseline: `{report.baseline_name}` `{report.baseline_version}`",
            f"- Candidate: `{report.candidate_name}` `{report.candidate_version}`",
            f"- Scenarios: {report.summary.scenarios}",
            f"- Observed privilege expansions: {report.summary.privilege_expansions}",
            f"- New allows: {report.summary.new_allows}",
            f"- Approval bypasses: {report.summary.approval_bypasses}",
            f"- Static authority expansions: {report.summary.static_authority_expansions}",
            f"- Static authority unknowns: {report.summary.static_authority_unknowns}",
            f"- Candidate rules without observed coverage: "
            f"{len(report.candidate_coverage.uncovered_rules)}",
            "",
            "## Permission changes",
            "",
            "| Scenario | Risk | Baseline | Candidate | Direction | Rule change |",
            "|---|---|---|---|---|---|",
        ]
        changed = [item for item in report.transitions if item.changed]
        if changed:
            for item in changed:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _escape_markdown(item.scenario_id),
                            item.risk.value,
                            item.baseline_effect.value,
                            item.candidate_effect.value,
                            item.direction.value,
                            _escape_markdown(
                                f"{item.baseline_rule_id or 'default'} → "
                                f"{item.candidate_rule_id or 'default'}"
                            ),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| _none_ | - | - | - | - | - |")

        lines.extend(["", "## Static authority analysis", ""])
        if report.authority_findings:
            lines.extend(
                [
                    "| Kind | Code | Baseline rule | Candidate rule | Finding | Fingerprint |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for finding in report.authority_findings:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            finding.kind.value,
                            finding.code,
                            _escape_markdown(finding.baseline_rule_id or "-"),
                            _escape_markdown(finding.candidate_rule_id or "-"),
                            _escape_markdown(finding.message),
                            f"`{finding.fingerprint[:12]}`",
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("- No expansion or unknown finding in the bounded static model.")

        lines.extend(["", "## Structural policy diff", ""])
        lines.append(f"- Added rules: {_inline(report.structural_diff.added_rules)}")
        lines.append(f"- Removed rules: {_inline(report.structural_diff.removed_rules)}")
        lines.append(f"- Modified semantic rules: {_inline(report.structural_diff.modified_rules)}")
        lines.append(f"- Shared rules reordered: `{report.structural_diff.reordered_rules}`")
        lines.append(f"- Default effect changed: `{report.structural_diff.default_effect_changed}`")
        lines.extend(["", "## Candidate coverage", ""])
        lines.append(
            "Observed scenario coverage is evidence of exercised rules, not exhaustive policy coverage."
        )
        lines.append("")
        for rule_id, hits in report.candidate_coverage.rule_hits.items():
            lines.append(f"- `{rule_id}`: {hits} hit(s)")
        lines.append(f"- `default`: {report.candidate_coverage.default_hits} hit(s)")

        if self.gate is not None:
            lines.extend(["", "## Gate", ""])
            if self.gate.violations:
                for violation in self.gate.violations:
                    lines.append(
                        f"- **{violation.code}**: {violation.message} "
                        f"(actual `{violation.actual}`, limit `{violation.limit}`)"
                    )
            else:
                lines.append("- No violations.")
            if self.gate.waived_scenarios:
                lines.append("- Waived scenarios: " + _inline(self.gate.waived_scenarios))
            if self.gate.waived_authority_findings:
                lines.append(
                    "- Waived static authority findings: "
                    + _inline([item[:12] for item in self.gate.waived_authority_findings])
                )
            if self.gate.expired_waivers:
                lines.append("- Expired waivers: " + _inline(self.gate.expired_waivers))
            if self.gate.unused_waivers:
                lines.append("- Unused waivers: " + _inline(self.gate.unused_waivers))
        return "\n".join(lines) + "\n"

    def sarif(self, candidate_path: str | Path = "candidate-policy.yaml") -> str:
        results: list[dict[str, Any]] = []
        waived_scenarios = set(self.gate.waived_scenarios) if self.gate is not None else set()
        waived_authority = (
            set(self.gate.waived_authority_findings) if self.gate is not None else set()
        )
        for item in self.report.transitions:
            if not item.privilege_expansion or item.scenario_id in waived_scenarios:
                continue
            results.append(_transition_sarif(item, str(candidate_path)))
        for finding in self.report.authority_findings:
            if finding.fingerprint in waived_authority:
                continue
            results.append(_authority_sarif(finding, str(candidate_path)))
        for rule_id in self.report.candidate_coverage.uncovered_rules:
            results.append(
                {
                    "ruleId": "permitdiff/uncovered-rule",
                    "level": "warning",
                    "message": {
                        "text": f"Candidate rule {rule_id!r} has no observed corpus coverage."
                    },
                    "locations": [_sarif_location(str(candidate_path))],
                    "properties": {"rule_id": rule_id},
                }
            )
        payload = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "PermitDiff",
                            "informationUri": "https://github.com/TensorScholar/permitdiff",
                            "version": __version__,
                            "rules": [
                                {
                                    "id": "permitdiff/privilege-expansion",
                                    "shortDescription": {
                                        "text": "Observed AI-agent permission became more permissive"
                                    },
                                },
                                {
                                    "id": "permitdiff/static-authority-expansion",
                                    "shortDescription": {
                                        "text": "Static analysis found a potential authority expansion"
                                    },
                                },
                                {
                                    "id": "permitdiff/static-authority-unknown",
                                    "shortDescription": {
                                        "text": "Static analysis cannot prove the change non-expanding"
                                    },
                                },
                                {
                                    "id": "permitdiff/uncovered-rule",
                                    "shortDescription": {
                                        "text": (
                                            "Candidate policy rule lacks observed corpus coverage"
                                        )
                                    },
                                },
                            ],
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def console(self, max_changes: int = 50) -> str:
        stream = io.StringIO()
        console = Console(
            file=stream,
            force_terminal=False,
            color_system=None,
            width=120,
        )
        report = self.report
        verdict = _verdict(self.gate)
        console.print(
            f"PermitDiff: {report.baseline_version} → {report.candidate_version} [{verdict}]"
        )
        summary = Table(show_header=False, box=None)
        summary.add_row("Scenarios", str(report.summary.scenarios))
        summary.add_row("Observed privilege expansions", str(report.summary.privilege_expansions))
        summary.add_row("New allows", str(report.summary.new_allows))
        summary.add_row("Approval bypasses", str(report.summary.approval_bypasses))
        summary.add_row("Restrictions", str(report.summary.restrictions))
        summary.add_row(
            "Static authority expansions", str(report.summary.static_authority_expansions)
        )
        summary.add_row("Static authority unknowns", str(report.summary.static_authority_unknowns))
        summary.add_row(
            "Uncovered candidate rules",
            str(len(report.candidate_coverage.uncovered_rules)),
        )
        console.print(summary)

        changed = [item for item in report.transitions if item.changed]
        table = Table(title="Observed permission changes")
        table.add_column("Scenario")
        table.add_column("Risk")
        table.add_column("Baseline")
        table.add_column("Candidate")
        table.add_column("Direction")
        table.add_column("Rules")
        for item in changed[:max_changes]:
            table.add_row(
                item.scenario_id,
                item.risk.value,
                item.baseline_effect.value,
                item.candidate_effect.value,
                item.direction.value,
                f"{item.baseline_rule_id or 'default'} → {item.candidate_rule_id or 'default'}",
            )
        if not changed:
            table.add_row("none", "-", "-", "-", "-", "-")
        console.print(table)
        if len(changed) > max_changes:
            console.print(f"Showing {max_changes} of {len(changed)} changed scenarios.")

        if report.authority_findings:
            authority = Table(title="Static authority findings")
            authority.add_column("Kind")
            authority.add_column("Code")
            authority.add_column("Rules")
            authority.add_column("Finding")
            for finding in report.authority_findings[:max_changes]:
                authority.add_row(
                    finding.kind.value,
                    finding.code,
                    f"{finding.baseline_rule_id or '-'} → {finding.candidate_rule_id or '-'}",
                    finding.message,
                )
            console.print(authority)
            if len(report.authority_findings) > max_changes:
                console.print(
                    f"Showing {max_changes} of {len(report.authority_findings)} static findings."
                )

        if self.gate is not None and self.gate.violations:
            violations = Table(title="Gate violations")
            violations.add_column("Code")
            violations.add_column("Actual")
            violations.add_column("Limit")
            violations.add_column("Message")
            for violation in self.gate.violations:
                violations.add_row(
                    violation.code,
                    str(violation.actual),
                    str(violation.limit),
                    violation.message,
                )
            console.print(violations)
        return stream.getvalue()


def _transition_sarif(item: ScenarioTransition, candidate_path: str) -> dict[str, Any]:
    level = "error" if item.severity.value in {"high", "critical"} else "warning"
    return {
        "ruleId": "permitdiff/privilege-expansion",
        "level": level,
        "message": {
            "text": (
                f"Scenario {item.scenario_id!r} changed from {item.baseline_effect.value} "
                f"to {item.candidate_effect.value} ({item.risk.value} risk)."
            )
        },
        "locations": [_sarif_location(candidate_path)],
        "properties": {
            "scenario_id": item.scenario_id,
            "risk": item.risk.value,
            "severity": item.severity.value,
            "baseline_rule_id": item.baseline_rule_id,
            "candidate_rule_id": item.candidate_rule_id,
            "action_fingerprint": item.action_fingerprint,
        },
    }


def _authority_sarif(item: AuthorityFinding, candidate_path: str) -> dict[str, Any]:
    rule_id = (
        "permitdiff/static-authority-expansion"
        if item.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
        else "permitdiff/static-authority-unknown"
    )
    return {
        "ruleId": rule_id,
        "level": "error",
        "message": {"text": item.message},
        "locations": [_sarif_location(candidate_path)],
        "properties": {
            "finding_kind": item.kind.value,
            "finding_code": item.code,
            "finding_fingerprint": item.fingerprint,
            "baseline_rule_id": item.baseline_rule_id,
            "candidate_rule_id": item.candidate_rule_id,
            "match_relation": item.match_relation.value
            if item.match_relation is not None
            else None,
        },
    }


def _sarif_location(path: str) -> dict[str, Any]:
    return {"physicalLocation": {"artifactLocation": {"uri": path}}}


def _verdict(gate: GateResult | None) -> str:
    if gate is None:
        return "REPORT ONLY"
    return "PASS" if gate.passed else "FAIL"


def _inline(values: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in values) if values else "_none_"


def _escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
