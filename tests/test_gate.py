from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from permitdiff.analysis import ComparisonReport, compare_policies
from permitdiff.authority import AuthorityFindingKind
from permitdiff.errors import GateLoadError
from permitdiff.gate import (
    AuthorityWaiver,
    GateConfig,
    TransitionWaiver,
    evaluate_gate,
    strict_gate,
)
from permitdiff.models import DecisionEffect, Scenario
from permitdiff.policy import PolicyDocument, RuleMatch


def _report(baseline: PolicyDocument, candidate: PolicyDocument, scenarios: list[Scenario]):
    return compare_policies(baseline, candidate, scenarios)


def _waiver(
    expires_on: date,
    *,
    action_fingerprint: str = "0" * 64,
    baseline_digest: str = "0" * 64,
    candidate_digest: str = "1" * 64,
) -> TransitionWaiver:
    return TransitionWaiver(
        id="approved-refund",
        scenario_id="refund-50",
        from_effect=DecisionEffect.REQUIRE_APPROVAL,
        to_effect=DecisionEffect.ALLOW,
        action_fingerprint=action_fingerprint,
        baseline_digest=baseline_digest,
        candidate_digest=candidate_digest,
        reason="Payments Risk approved this exact staged permission change.",
        expires_on=expires_on,
    )


def _transition_waiver_for_report(
    report: ComparisonReport,
    expires_on: date,
    *,
    waiver_id: str = "approved-refund",
) -> TransitionWaiver:
    transition = next(item for item in report.transitions if item.scenario_id == "refund-50")
    return TransitionWaiver(
        id=waiver_id,
        scenario_id=transition.scenario_id,
        from_effect=transition.baseline_effect,
        to_effect=transition.candidate_effect,
        action_fingerprint=transition.action_fingerprint,
        baseline_digest=report.baseline_digest,
        candidate_digest=report.candidate_digest,
        reason="Payments Risk approved this exact staged permission change.",
        expires_on=expires_on,
    )


def _authority_waiver(
    report: ComparisonReport,
    expires_on: date,
    *,
    waiver_id: str = "approved-static-refund-rule",
    candidate_digest: str | None = None,
) -> AuthorityWaiver:
    finding = report.authority_findings[0]
    return AuthorityWaiver(
        id=waiver_id,
        finding_kind=finding.kind,
        finding_fingerprint=finding.fingerprint,
        baseline_digest=report.baseline_digest,
        candidate_digest=candidate_digest or report.candidate_digest,
        reason="Security review approved this exact policy-level authority change.",
        expires_on=expires_on,
    )


def test_strict_gate_blocks_expansion(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    result = evaluate_gate(_report(baseline, candidate, scenarios), strict_gate())
    assert not result.passed
    assert {item.code for item in result.violations} >= {
        "privilege_expansions",
        "new_allows",
        "approval_bypasses",
        "static_authority_expansions",
    }


def test_exact_active_waivers_allow_observed_and_static_expansion(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    report = _report(baseline, candidate, scenarios)
    config = GateConfig(
        waivers=[
            _transition_waiver_for_report(report, today + timedelta(days=7)),
        ],
        authority_waivers=[_authority_waiver(report, today + timedelta(days=7))],
    )
    result = evaluate_gate(report, config, today=today)
    assert result.passed
    assert result.waived_scenarios == ["refund-50"]
    assert result.waived_authority_findings == [report.authority_findings[0].fingerprint]


def test_transition_waiver_does_not_waive_policy_level_authority_expansion(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    report = _report(baseline, candidate, scenarios)
    result = evaluate_gate(
        report,
        GateConfig(
            waivers=[
                _transition_waiver_for_report(report, today + timedelta(days=7)),
            ]
        ),
        today=today,
    )
    assert not result.passed
    assert "static_authority_expansions" in {item.code for item in result.violations}


def test_waiver_does_not_apply_after_action_fingerprint_changes(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    original_report = _report(baseline, candidate, scenarios)
    original = next(item for item in scenarios if item.id == "refund-50")
    changed = original.model_copy(
        update={
            "action": original.action.model_copy(
                update={
                    "arguments": {
                        **original.action.arguments,
                        "__waiver_drift_probe__": "changed",
                    }
                }
            )
        }
    )
    changed_scenarios = [changed if item.id == original.id else item for item in scenarios]

    config = GateConfig(
        waivers=[
            _transition_waiver_for_report(original_report, today + timedelta(days=7)),
        ],
        authority_waivers=[_authority_waiver(original_report, today + timedelta(days=7))],
    )
    result = evaluate_gate(
        _report(baseline, candidate, changed_scenarios),
        config,
        today=today,
    )

    assert not result.passed
    assert result.unused_waivers == ["approved-refund"]


def test_authority_waiver_does_not_replay_after_candidate_digest_changes(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    original_report = _report(baseline, candidate, scenarios)
    drifted_metadata = candidate.metadata.model_copy(update={"version": "1.1.1"})
    drifted_candidate = candidate.model_copy(update={"metadata": drifted_metadata})
    drifted_report = _report(baseline, drifted_candidate, scenarios)
    assert (
        original_report.authority_findings[0].fingerprint
        == drifted_report.authority_findings[0].fingerprint
    )
    result = evaluate_gate(
        drifted_report,
        GateConfig(
            max_privilege_expansions=10,
            max_new_allows=10,
            max_approval_bypasses=10,
            authority_waivers=[_authority_waiver(original_report, today + timedelta(days=7))],
        ),
        today=today,
    )
    assert not result.passed
    assert "static_authority_expansions" in {item.code for item in result.violations}
    assert result.unused_waivers == ["approved-static-refund-rule"]


def test_transition_waiver_does_not_replay_after_candidate_digest_changes(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    original_report = _report(baseline, candidate, scenarios)
    drifted_metadata = candidate.metadata.model_copy(update={"version": "1.1.1"})
    drifted_candidate = candidate.model_copy(update={"metadata": drifted_metadata})
    drifted_report = _report(baseline, drifted_candidate, scenarios)
    original_transition = next(
        item for item in original_report.transitions if item.scenario_id == "refund-50"
    )
    drifted_transition = next(
        item for item in drifted_report.transitions if item.scenario_id == "refund-50"
    )
    assert drifted_transition.baseline_effect is original_transition.baseline_effect
    assert drifted_transition.candidate_effect is original_transition.candidate_effect
    assert drifted_transition.action_fingerprint == original_transition.action_fingerprint
    assert drifted_report.candidate_digest != original_report.candidate_digest
    result = evaluate_gate(
        drifted_report,
        GateConfig(
            max_static_authority_expansions=10,
            authority_waivers=[_authority_waiver(drifted_report, today + timedelta(days=7))],
            waivers=[
                _transition_waiver_for_report(original_report, today + timedelta(days=7)),
            ],
        ),
        today=today,
    )
    assert not result.passed
    assert "privilege_expansions" in {item.code for item in result.violations}
    assert result.unused_waivers == ["approved-refund"]


def test_transition_waiver_does_not_replay_after_baseline_digest_changes(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    original_report = _report(baseline, candidate, scenarios)
    drifted_metadata = baseline.metadata.model_copy(update={"version": "9.9.9"})
    drifted_baseline = baseline.model_copy(update={"metadata": drifted_metadata})
    drifted_report = _report(drifted_baseline, candidate, scenarios)
    original_transition = next(
        item for item in original_report.transitions if item.scenario_id == "refund-50"
    )
    drifted_transition = next(
        item for item in drifted_report.transitions if item.scenario_id == "refund-50"
    )
    assert drifted_transition.baseline_effect is original_transition.baseline_effect
    assert drifted_transition.candidate_effect is original_transition.candidate_effect
    assert drifted_transition.action_fingerprint == original_transition.action_fingerprint
    assert drifted_report.baseline_digest != original_report.baseline_digest
    result = evaluate_gate(
        drifted_report,
        GateConfig(
            max_static_authority_expansions=10,
            authority_waivers=[_authority_waiver(drifted_report, today + timedelta(days=7))],
            waivers=[
                _transition_waiver_for_report(original_report, today + timedelta(days=7)),
            ],
        ),
        today=today,
    )
    assert not result.passed
    assert "privilege_expansions" in {item.code for item in result.violations}
    assert result.unused_waivers == ["approved-refund"]


def test_same_transition_outcome_under_different_digests_cannot_reuse_waiver(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    original_report = _report(baseline, candidate, scenarios)
    relabeled_rules = [
        rule.model_copy(update={"description": f"{rule.description} (rev B)."})
        for rule in candidate.rules
    ]
    relabeled_candidate = candidate.model_copy(update={"rules": relabeled_rules})
    relabeled_report = _report(baseline, relabeled_candidate, scenarios)
    original_transition = next(
        item for item in original_report.transitions if item.scenario_id == "refund-50"
    )
    relabeled_transition = next(
        item for item in relabeled_report.transitions if item.scenario_id == "refund-50"
    )
    assert relabeled_transition.baseline_effect is original_transition.baseline_effect
    assert relabeled_transition.candidate_effect is original_transition.candidate_effect
    assert relabeled_transition.action_fingerprint == original_transition.action_fingerprint
    assert relabeled_report.candidate_digest != original_report.candidate_digest
    assert len(relabeled_report.authority_findings) == len(original_report.authority_findings) == 1
    assert (
        relabeled_report.authority_findings[0].fingerprint
        == original_report.authority_findings[0].fingerprint
    )
    result = evaluate_gate(
        relabeled_report,
        GateConfig(
            authority_waivers=[_authority_waiver(relabeled_report, today + timedelta(days=7))],
            waivers=[
                _transition_waiver_for_report(original_report, today + timedelta(days=7)),
            ],
        ),
        today=today,
    )
    assert not result.passed
    assert "privilege_expansions" in {item.code for item in result.violations}
    assert result.unused_waivers == ["approved-refund"]


def test_transition_waiver_without_digests_fails_validation() -> None:
    with pytest.raises(ValidationError, match="baseline_digest"):
        TransitionWaiver(
            id="legacy-waiver",
            scenario_id="refund-50",
            from_effect=DecisionEffect.REQUIRE_APPROVAL,
            to_effect=DecisionEffect.ALLOW,
            action_fingerprint="0" * 64,
            reason="Legacy waiver without digest binding must not validate.",
            expires_on=date(2026, 8, 1),
        )


def test_legacy_gate_yaml_without_transition_digests_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        """api_version: permitdiff.dev/v1alpha1
kind: Gate
waivers:
  - id: legacy-waiver
    scenario_id: refund-50
    from_effect: require_approval
    to_effect: allow
    action_fingerprint: '0000000000000000000000000000000000000000000000000000000000000000'
    reason: Legacy waiver without digest binding must not validate.
    expires_on: 2026-08-01
""",
        encoding="utf-8",
    )
    with pytest.raises(GateLoadError, match="baseline_digest"):
        GateConfig.from_yaml(path)


def test_expired_waiver_does_not_apply(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    config = GateConfig(waivers=[_waiver(today - timedelta(days=1))])
    result = evaluate_gate(_report(baseline, candidate, scenarios), config, today=today)
    assert not result.passed
    assert result.expired_waivers == ["approved-refund"]


def test_waiver_must_match_exact_transition(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    report = _report(baseline, candidate, scenarios)
    wrong = _transition_waiver_for_report(report, today + timedelta(days=7)).model_copy(
        update={"to_effect": DecisionEffect.REQUIRE_APPROVAL}
    )
    result = evaluate_gate(
        _report(baseline, candidate, scenarios),
        GateConfig(waivers=[wrong]),
        today=today,
    )
    assert not result.passed
    assert result.unused_waivers == ["approved-refund"]


def test_unused_waiver_can_fail_gate(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    waiver = _waiver(today + timedelta(days=7)).model_copy(update={"scenario_id": "missing"})
    config = GateConfig(
        max_privilege_expansions=1,
        max_new_allows=1,
        max_approval_bypasses=1,
        max_static_authority_expansions=1,
        fail_on_unused_waivers=True,
        waivers=[waiver],
    )
    result = evaluate_gate(_report(baseline, candidate, scenarios), config, today=today)
    assert "unused_waivers" in {item.code for item in result.violations}


def test_uncovered_candidate_rule_fails_gate(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    extra = candidate.rules[0].model_copy(
        update={"id": "never-hit", "match": RuleMatch(tools=["never.*"])}
    )
    candidate_with_gap = candidate.model_copy(update={"rules": [*candidate.rules, extra]})
    report = _report(baseline, candidate_with_gap, scenarios)
    result = evaluate_gate(
        report,
        GateConfig(
            max_privilege_expansions=1,
            max_new_allows=1,
            max_approval_bypasses=1,
            max_static_authority_expansions=10,
        ),
    )
    assert "uncovered_candidate_rules" in {item.code for item in result.violations}


def test_gate_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        """api_version: permitdiff.dev/v1alpha1
kind: Gate
max_privilege_expansions: 1
waivers: []
authority_waivers: []
""",
        encoding="utf-8",
    )
    assert GateConfig.from_yaml(path).max_privilege_expansions == 1


def test_duplicate_yaml_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        """api_version: permitdiff.dev/v1alpha1
kind: Gate
max_privilege_expansions: 0
max_privilege_expansions: 999
""",
        encoding="utf-8",
    )
    with pytest.raises(
        GateLoadError,
        match="found duplicate key 'max_privilege_expansions'",
    ):
        GateConfig.from_yaml(path)


def test_invalid_gate_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(GateLoadError, match="root must be a mapping"):
        GateConfig.from_yaml(path)


def test_duplicate_waiver_ids_are_rejected() -> None:
    waiver = _waiver(date(2026, 8, 1))
    with pytest.raises(ValidationError, match="waiver ids must be unique"):
        GateConfig(waivers=[waiver, waiver])


def test_duplicate_ids_across_waiver_types_are_rejected(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    report = _report(baseline, candidate, scenarios)
    transition = _waiver(date(2026, 8, 1))
    authority = _authority_waiver(
        report,
        date(2026, 8, 1),
        waiver_id=transition.id,
    )
    with pytest.raises(ValidationError, match="waiver ids must be unique"):
        GateConfig(waivers=[transition], authority_waivers=[authority])


def test_default_effect_relaxation_fails_without_observed_default_hit(
    baseline: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    candidate = baseline.model_copy(update={"default_effect": DecisionEffect.ALLOW})
    covered = [item for item in scenarios if item.id != "unknown-tool"]
    report = _report(baseline, candidate, covered)
    config = GateConfig(
        max_privilege_expansions=10,
        max_new_allows=10,
        max_approval_bypasses=10,
        max_static_authority_expansions=10,
    )
    result = evaluate_gate(report, config)
    assert "default_effect_relaxation" in {item.code for item in result.violations}


def test_static_unknown_fails_closed_even_when_expansion_thresholds_are_relaxed(
    baseline: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    candidate = baseline.model_copy(update={"rules": list(reversed(baseline.rules))})
    report = _report(baseline, candidate, scenarios)
    assert any(item.kind is AuthorityFindingKind.UNKNOWN for item in report.authority_findings)
    result = evaluate_gate(
        report,
        GateConfig(
            max_privilege_expansions=100,
            max_new_allows=100,
            max_approval_bypasses=100,
            max_static_authority_expansions=100,
            max_uncovered_candidate_rules=None,
        ),
    )
    assert "static_authority_unknown" in {item.code for item in result.violations}


def test_duplicate_transition_waivers_are_rejected() -> None:
    first = _waiver(date(2026, 8, 1))
    second = first.model_copy(update={"id": "second-approval"})
    with pytest.raises(ValidationError, match="unique scenario transitions"):
        GateConfig(waivers=[first, second])


def test_same_transition_with_different_digests_is_distinct() -> None:
    first = _waiver(date(2026, 8, 1))
    second = first.model_copy(
        update={"id": "second-approval", "candidate_digest": "2" * 64},
    )
    config = GateConfig(waivers=[first, second])
    assert {item.id for item in config.waivers} == {"approved-refund", "second-approval"}


def test_duplicate_authority_waivers_are_rejected(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    report = _report(baseline, candidate, scenarios)
    first = _authority_waiver(report, date(2026, 8, 1))
    second = first.model_copy(update={"id": "second-static-approval"})
    with pytest.raises(ValidationError, match="unique static findings"):
        GateConfig(authority_waivers=[first, second])
