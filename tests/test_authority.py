from __future__ import annotations

from permitdiff.authority import (
    AuthorityFindingKind,
    MatchRelation,
    analyze_authority_changes,
)
from permitdiff.models import DecisionEffect
from permitdiff.policy import PolicyDocument, PolicyMetadata, PolicyRule, Predicate, RuleMatch


def _policy(*rules: PolicyRule, default: DecisionEffect = DecisionEffect.DENY) -> PolicyDocument:
    return PolicyDocument(
        metadata=PolicyMetadata(name="test", version="1"),
        default_effect=default,
        rules=list(rules),
    )


def _rule(
    *,
    rule_id: str = "target",
    effect: DecisionEffect = DecisionEffect.ALLOW,
    tools: list[str] | None = None,
    arguments: list[Predicate] | None = None,
    description: str = "test rule",
) -> PolicyRule:
    return PolicyRule(
        id=rule_id,
        description=description,
        effect=effect,
        match=RuleMatch(
            tools=tools or ["payments.refund"],
            arguments=arguments or [],
        ),
    )


def _only_finding(baseline: PolicyDocument, candidate: PolicyDocument):
    findings = analyze_authority_changes(baseline, candidate)
    assert len(findings) == 1
    return findings[0]


def test_specific_tool_to_wildcard_is_static_expansion() -> None:
    finding = _only_finding(
        _policy(_rule(tools=["payments.refund"])),
        _policy(_rule(tools=["payments.*"])),
    )
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
    assert finding.code == "rule_scope_broadened"
    assert finding.match_relation is MatchRelation.BROADER


def test_numeric_upper_bound_relaxation_is_static_expansion() -> None:
    finding = _only_finding(
        _policy(
            _rule(
                arguments=[
                    Predicate(path="amount", operator="less_than_or_equal", value=100)
                ]
            )
        ),
        _policy(
            _rule(
                arguments=[
                    Predicate(path="amount", operator="less_than_or_equal", value=10_000)
                ]
            )
        ),
    )
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
    assert finding.match_relation is MatchRelation.BROADER


def test_constraint_removal_is_static_expansion() -> None:
    finding = _only_finding(
        _policy(
            _rule(
                arguments=[Predicate(path="tenant", operator="equals", value="alpha")]
            )
        ),
        _policy(_rule(arguments=[])),
    )
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
    assert finding.match_relation is MatchRelation.BROADER


def test_narrowing_a_deny_rule_is_static_expansion() -> None:
    finding = _only_finding(
        _policy(_rule(effect=DecisionEffect.DENY, tools=["payments.*"])),
        _policy(_rule(effect=DecisionEffect.DENY, tools=["payments.refund"])),
    )
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
    assert finding.match_relation is MatchRelation.NARROWER


def test_mixed_effect_reorder_is_unknown_and_fail_closed_evidence() -> None:
    deny = _rule(rule_id="deny", effect=DecisionEffect.DENY, tools=["payments.*"])
    allow = _rule(rule_id="allow", effect=DecisionEffect.ALLOW, tools=["payments.refund"])
    finding = _only_finding(_policy(deny, allow), _policy(allow, deny))
    assert finding.kind is AuthorityFindingKind.UNKNOWN
    assert finding.code == "rule_order_changed"


def test_ambiguous_glob_relation_remains_unknown() -> None:
    finding = _only_finding(
        _policy(_rule(tools=["payments.*"])),
        _policy(_rule(tools=["pay*.refund"])),
    )
    assert finding.kind is AuthorityFindingKind.UNKNOWN
    assert finding.match_relation is MatchRelation.UNKNOWN


def test_description_only_change_has_no_authority_finding() -> None:
    baseline = _policy(_rule(description="old explanation"))
    candidate = _policy(_rule(description="new explanation"))
    assert analyze_authority_changes(baseline, candidate) == []


def test_semantically_identical_rule_rename_has_no_authority_finding() -> None:
    baseline = _policy(_rule(rule_id="old-id"))
    candidate = _policy(_rule(rule_id="new-id"))
    assert analyze_authority_changes(baseline, candidate) == []


def test_allow_scope_narrowing_is_not_reported_as_expansion() -> None:
    baseline = _policy(_rule(tools=["payments.*"]))
    candidate = _policy(_rule(tools=["payments.refund"]))
    assert analyze_authority_changes(baseline, candidate) == []
