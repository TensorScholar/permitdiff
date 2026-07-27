from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from permitdiff.analysis import compare_policies
from permitdiff.errors import GateLoadError
from permitdiff.gate import GateConfig, TransitionWaiver, evaluate_gate, strict_gate
from permitdiff.models import DecisionEffect, Scenario
from permitdiff.policy import PolicyDocument, RuleMatch


def _report(baseline: PolicyDocument, candidate: PolicyDocument, scenarios: list[Scenario]):
    return compare_policies(baseline, candidate, scenarios)


def _waiver(expires_on: date) -> TransitionWaiver:
    return TransitionWaiver(
        id="approved-refund",
        scenario_id="refund-50",
        from_effect=DecisionEffect.REQUIRE_APPROVAL,
        to_effect=DecisionEffect.ALLOW,
        reason="Payments Risk approved this exact staged permission change.",
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
    }


def test_exact_active_waiver_allows_transition(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> None:
    today = date(2026, 7, 27)
    config = GateConfig(waivers=[_waiver(today + timedelta(days=7))])
    result = evaluate_gate(_report(baseline, candidate, scenarios), config, today=today)
    assert result.passed
    assert result.waived_scenarios == ["refund-50"]


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
    wrong = _waiver(today + timedelta(days=7)).model_copy(
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
""",
        encoding="utf-8",
    )
    assert GateConfig.from_yaml(path).max_privilege_expansions == 1


def test_invalid_gate_is_wrapped(tmp_path: Path) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(GateLoadError, match="root must be a mapping"):
        GateConfig.from_yaml(path)


def test_duplicate_waiver_ids_are_rejected() -> None:
    waiver = _waiver(date(2026, 8, 1))
    with pytest.raises(ValidationError, match="waiver ids must be unique"):
        GateConfig(waivers=[waiver, waiver])


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
    )
    result = evaluate_gate(report, config)
    assert "default_effect_relaxation" in {item.code for item in result.violations}


def test_duplicate_transition_waivers_are_rejected() -> None:
    first = _waiver(date(2026, 8, 1))
    second = first.model_copy(update={"id": "second-approval"})
    with pytest.raises(ValidationError, match="unique scenario transitions"):
        GateConfig(waivers=[first, second])
