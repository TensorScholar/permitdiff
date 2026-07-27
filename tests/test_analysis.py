from __future__ import annotations

import pytest

from permitdiff.analysis import ChangeDirection, Severity, compare_policies
from permitdiff.models import DecisionEffect, Scenario
from permitdiff.policy import PolicyDocument


def _transition(report, scenario_id: str):
    return next(item for item in report.transitions if item.scenario_id == scenario_id)


def test_compare_detects_approval_bypass(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    report = compare_policies(baseline, candidate, scenarios)
    item = _transition(report, "refund-50")
    assert item.baseline_effect is DecisionEffect.REQUIRE_APPROVAL
    assert item.candidate_effect is DecisionEffect.ALLOW
    assert item.direction is ChangeDirection.EXPANDED
    assert item.severity is Severity.HIGH
    assert item.approval_bypass


def test_compare_summary_is_consistent(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    summary = compare_policies(baseline, candidate, scenarios).summary
    assert summary.scenarios == 5
    assert summary.changed_effects == 1
    assert summary.privilege_expansions == 1
    assert summary.new_allows == 1
    assert summary.approval_bypasses == 1


def test_candidate_rule_coverage_is_observed(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    coverage = compare_policies(baseline, candidate, scenarios).candidate_coverage
    assert coverage.rule_hits["allow-low-value-refunds"] == 1
    assert coverage.uncovered_rules == []
    assert coverage.default_hits == 1


def test_structural_diff_reports_added_and_modified_rules(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    structural = compare_policies(baseline, candidate, scenarios).structural_diff
    assert structural.added_rules == ["allow-low-value-refunds"]
    assert "review-destructive-actions" in structural.modified_rules
    assert structural.removed_rules == []


def test_same_policy_has_no_effect_changes(
    baseline: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    report = compare_policies(baseline, baseline, scenarios)
    assert report.summary.changed_effects == 0
    assert report.summary.privilege_expansions == 0
    assert not report.structural_diff.default_effect_changed


def test_rule_reorder_is_reported(
    baseline: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    candidate = baseline.model_copy(update={"rules": list(reversed(baseline.rules))})
    report = compare_policies(baseline, candidate, scenarios)
    assert report.structural_diff.reordered_rules


def test_restriction_is_classified(
    baseline: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    candidate = baseline.model_copy(update={"default_effect": DecisionEffect.DENY, "rules": []})
    report = compare_policies(baseline, candidate, scenarios)
    item = _transition(report, "customer-read")
    assert item.direction is ChangeDirection.RESTRICTED
    assert item.severity is Severity.NOTE


def test_empty_scenario_list_is_rejected(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
) -> None:
    with pytest.raises(ValueError, match="at least one"):
        compare_policies(baseline, candidate, [])


def test_corpus_digest_is_stable(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    first = compare_policies(baseline, candidate, scenarios)
    second = compare_policies(baseline, candidate, scenarios)
    assert first.corpus_digest == second.corpus_digest


def test_corpus_digest_ignores_ephemeral_action_fields(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    changed = scenarios[0].action.model_copy(
        update={
            "request_id": "different-request",
            "requested_at": scenarios[0].action.requested_at.replace(year=2030),
        }
    )
    alternate = [
        scenarios[0].model_copy(update={"action": changed}),
        *scenarios[1:],
    ]
    first = compare_policies(baseline, candidate, scenarios)
    second = compare_policies(baseline, candidate, alternate)
    assert first.corpus_digest == second.corpus_digest
    assert first.transitions[0].action_fingerprint == second.transitions[0].action_fingerprint
