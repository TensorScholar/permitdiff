"""Semantic comparison of effective permissions over an explicit scenario corpus."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from permitdiff.engine import PolicyEngine
from permitdiff.models import DecisionEffect, RiskLevel, Scenario
from permitdiff.policy import PolicyDocument

_EFFECT_RANK = {
    DecisionEffect.DENY: 0,
    DecisionEffect.REQUIRE_APPROVAL: 1,
    DecisionEffect.ALLOW: 2,
}


class ChangeDirection(StrEnum):
    """Whether candidate policy semantics expand or restrict permissions."""

    UNCHANGED = "unchanged"
    EXPANDED = "expanded"
    RESTRICTED = "restricted"


class Severity(StrEnum):
    """Review severity assigned to a permission transition."""

    NOTE = "note"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScenarioTransition(BaseModel):
    """Baseline-to-candidate decision transition for one scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    description: str | None
    owner: str | None
    tags: list[str]
    risk: RiskLevel
    action_fingerprint: str
    baseline_effect: DecisionEffect
    candidate_effect: DecisionEffect
    baseline_rule_id: str | None
    candidate_rule_id: str | None
    direction: ChangeDirection
    severity: Severity

    @property
    def changed(self) -> bool:
        return (
            self.baseline_effect is not self.candidate_effect
            or self.baseline_rule_id != self.candidate_rule_id
        )

    @property
    def privilege_expansion(self) -> bool:
        return self.direction is ChangeDirection.EXPANDED

    @property
    def new_allow(self) -> bool:
        return (
            self.candidate_effect is DecisionEffect.ALLOW
            and self.baseline_effect is not DecisionEffect.ALLOW
        )

    @property
    def approval_bypass(self) -> bool:
        return (
            self.baseline_effect is DecisionEffect.REQUIRE_APPROVAL
            and self.candidate_effect is DecisionEffect.ALLOW
        )


class RuleCoverage(BaseModel):
    """Observed rule hit counts for a policy over the corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_hits: dict[str, int]
    default_hits: int
    uncovered_rules: list[str]


class StructuralDiff(BaseModel):
    """Review-oriented structural changes between policy documents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    added_rules: list[str]
    removed_rules: list[str]
    modified_rules: list[str]
    reordered_rules: bool
    default_effect_changed: bool
    baseline_default_effect: DecisionEffect
    candidate_default_effect: DecisionEffect


class ComparisonSummary(BaseModel):
    """Aggregate counts used by humans and release gates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenarios: int
    unchanged_effects: int
    changed_effects: int
    privilege_expansions: int
    restrictions: int
    new_allows: int
    approval_bypasses: int


class ComparisonReport(BaseModel):
    """Complete deterministic comparison artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "permitdiff.report/v1alpha1"
    baseline_name: str
    baseline_version: str
    baseline_digest: str
    candidate_name: str
    candidate_version: str
    candidate_digest: str
    corpus_digest: str
    summary: ComparisonSummary
    structural_diff: StructuralDiff
    baseline_coverage: RuleCoverage
    candidate_coverage: RuleCoverage
    transitions: list[ScenarioTransition]


def compare_policies(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    scenarios: list[Scenario],
) -> ComparisonReport:
    """Evaluate the same corpus against both policies and compare effective permissions."""

    if not scenarios:
        raise ValueError("at least one scenario is required")
    baseline_engine = PolicyEngine(baseline)
    candidate_engine = PolicyEngine(candidate)
    baseline_hits: Counter[str] = Counter()
    candidate_hits: Counter[str] = Counter()
    baseline_default_hits = 0
    candidate_default_hits = 0
    transitions: list[ScenarioTransition] = []

    for scenario in scenarios:
        baseline_decision = baseline_engine.evaluate(scenario.action)
        candidate_decision = candidate_engine.evaluate(scenario.action)
        if baseline_decision.rule_id is None:
            baseline_default_hits += 1
        else:
            baseline_hits[baseline_decision.rule_id] += 1
        if candidate_decision.rule_id is None:
            candidate_default_hits += 1
        else:
            candidate_hits[candidate_decision.rule_id] += 1

        direction = _direction(baseline_decision.effect, candidate_decision.effect)
        transitions.append(
            ScenarioTransition(
                scenario_id=scenario.id,
                description=scenario.description,
                owner=scenario.owner,
                tags=scenario.tags,
                risk=scenario.risk,
                action_fingerprint=scenario.action.fingerprint(),
                baseline_effect=baseline_decision.effect,
                candidate_effect=candidate_decision.effect,
                baseline_rule_id=baseline_decision.rule_id,
                candidate_rule_id=candidate_decision.rule_id,
                direction=direction,
                severity=_severity(
                    baseline_decision.effect,
                    candidate_decision.effect,
                    scenario.risk,
                ),
            )
        )

    changed_effects = sum(item.baseline_effect is not item.candidate_effect for item in transitions)
    expansions = sum(item.privilege_expansion for item in transitions)
    restrictions = sum(item.direction is ChangeDirection.RESTRICTED for item in transitions)
    summary = ComparisonSummary(
        scenarios=len(transitions),
        unchanged_effects=len(transitions) - changed_effects,
        changed_effects=changed_effects,
        privilege_expansions=expansions,
        restrictions=restrictions,
        new_allows=sum(item.new_allow for item in transitions),
        approval_bypasses=sum(item.approval_bypass for item in transitions),
    )

    return ComparisonReport(
        baseline_name=baseline.metadata.name,
        baseline_version=baseline.metadata.version,
        baseline_digest=baseline.digest(),
        candidate_name=candidate.metadata.name,
        candidate_version=candidate.metadata.version,
        candidate_digest=candidate.digest(),
        corpus_digest=_corpus_digest(scenarios),
        summary=summary,
        structural_diff=_structural_diff(baseline, candidate),
        baseline_coverage=_coverage(baseline, baseline_hits, baseline_default_hits),
        candidate_coverage=_coverage(candidate, candidate_hits, candidate_default_hits),
        transitions=transitions,
    )


def _direction(baseline: DecisionEffect, candidate: DecisionEffect) -> ChangeDirection:
    delta = _EFFECT_RANK[candidate] - _EFFECT_RANK[baseline]
    if delta > 0:
        return ChangeDirection.EXPANDED
    if delta < 0:
        return ChangeDirection.RESTRICTED
    return ChangeDirection.UNCHANGED


def _severity(
    baseline: DecisionEffect,
    candidate: DecisionEffect,
    risk: RiskLevel,
) -> Severity:
    if baseline is candidate:
        return Severity.NOTE
    if _EFFECT_RANK[candidate] < _EFFECT_RANK[baseline]:
        return Severity.NOTE
    if baseline is DecisionEffect.REQUIRE_APPROVAL and candidate is DecisionEffect.ALLOW:
        return {
            RiskLevel.LOW: Severity.MEDIUM,
            RiskLevel.MEDIUM: Severity.HIGH,
            RiskLevel.HIGH: Severity.HIGH,
            RiskLevel.CRITICAL: Severity.CRITICAL,
        }[risk]
    if baseline is DecisionEffect.DENY and candidate is DecisionEffect.ALLOW:
        return {
            RiskLevel.LOW: Severity.MEDIUM,
            RiskLevel.MEDIUM: Severity.HIGH,
            RiskLevel.HIGH: Severity.CRITICAL,
            RiskLevel.CRITICAL: Severity.CRITICAL,
        }[risk]
    return {
        RiskLevel.LOW: Severity.LOW,
        RiskLevel.MEDIUM: Severity.MEDIUM,
        RiskLevel.HIGH: Severity.HIGH,
        RiskLevel.CRITICAL: Severity.HIGH,
    }[risk]


def _coverage(policy: PolicyDocument, hits: Counter[str], default_hits: int) -> RuleCoverage:
    rule_hits = {rule.id: hits[rule.id] for rule in policy.rules}
    return RuleCoverage(
        rule_hits=rule_hits,
        default_hits=default_hits,
        uncovered_rules=[rule_id for rule_id, count in rule_hits.items() if count == 0],
    )


def _structural_diff(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
) -> StructuralDiff:
    baseline_by_id = {rule.id: rule for rule in baseline.rules}
    candidate_by_id = {rule.id: rule for rule in candidate.rules}
    shared = baseline_by_id.keys() & candidate_by_id.keys()
    modified = [
        rule_id
        for rule_id in shared
        if baseline_by_id[rule_id].model_dump(mode="json")
        != candidate_by_id[rule_id].model_dump(mode="json")
    ]
    baseline_shared_order = [rule.id for rule in baseline.rules if rule.id in shared]
    candidate_shared_order = [rule.id for rule in candidate.rules if rule.id in shared]
    return StructuralDiff(
        added_rules=sorted(candidate_by_id.keys() - baseline_by_id.keys()),
        removed_rules=sorted(baseline_by_id.keys() - candidate_by_id.keys()),
        modified_rules=sorted(modified),
        reordered_rules=baseline_shared_order != candidate_shared_order,
        default_effect_changed=baseline.default_effect is not candidate.default_effect,
        baseline_default_effect=baseline.default_effect,
        candidate_default_effect=candidate.default_effect,
    )


def _corpus_digest(scenarios: list[Scenario]) -> str:
    normalized: list[dict[str, object]] = []
    for scenario in scenarios:
        payload = scenario.model_dump(mode="json")
        action = payload["action"]
        if not isinstance(action, dict):  # pragma: no cover - enforced by the model
            raise TypeError("scenario action must serialize as an object")
        action.pop("request_id", None)
        action.pop("requested_at", None)
        normalized.append(payload)
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
