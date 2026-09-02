from __future__ import annotations

import pytest
from pydantic import ValidationError

from permitdiff.authority import (
    AuthorityFindingKind,
    MatchRelation,
    analyze_authority_changes,
    match_relation,
)
from permitdiff.models import DecisionEffect, RiskLevel
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
            _rule(arguments=[Predicate(path="amount", operator="less_than_or_equal", value=100)])
        ),
        _policy(
            _rule(arguments=[Predicate(path="amount", operator="less_than_or_equal", value=10_000)])
        ),
    )
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
    assert finding.match_relation is MatchRelation.BROADER


def test_constraint_removal_is_static_expansion() -> None:
    finding = _only_finding(
        _policy(_rule(arguments=[Predicate(path="tenant", operator="equals", value="alpha")])),
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


def test_same_effect_reorder_is_not_authority_noise() -> None:
    first = _rule(rule_id="first", tools=["payments.first"])
    second = _rule(rule_id="second", tools=["payments.second"])
    assert analyze_authority_changes(_policy(first, second), _policy(second, first)) == []


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


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected"),
    [
        (RuleMatch(tools=["a"]), RuleMatch(tools=["a"]), MatchRelation.EQUAL),
        (RuleMatch(tools=["a"]), RuleMatch(tools=["a", "b"]), MatchRelation.BROADER),
        (RuleMatch(tools=["a", "b"]), RuleMatch(tools=["a"]), MatchRelation.NARROWER),
        (RuleMatch(tools=["a"]), RuleMatch(tools=["b"]), MatchRelation.INCOMPARABLE),
        (RuleMatch(tools=["a"]), RuleMatch(tools=["*"]), MatchRelation.BROADER),
        (RuleMatch(tools=["*"]), RuleMatch(tools=["a"]), MatchRelation.NARROWER),
        (RuleMatch(tools=["pay.refund"]), RuleMatch(tools=["pay.*"]), MatchRelation.BROADER),
        (RuleMatch(tools=["pay.*"]), RuleMatch(tools=["pay.refund"]), MatchRelation.NARROWER),
        (RuleMatch(tools=["pay.[ab]"]), RuleMatch(tools=["pay.a"]), MatchRelation.UNKNOWN),
    ],
)
def test_match_relation_glob_and_finite_domains(
    baseline: RuleMatch,
    candidate: RuleMatch,
    expected: MatchRelation,
) -> None:
    assert match_relation(baseline, candidate) is expected


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected"),
    [
        (
            RuleMatch(risks=[RiskLevel.LOW]),
            RuleMatch(),
            MatchRelation.BROADER,
        ),
        (
            RuleMatch(),
            RuleMatch(risks=[RiskLevel.LOW]),
            MatchRelation.NARROWER,
        ),
        (
            RuleMatch(risks=[RiskLevel.LOW]),
            RuleMatch(risks=[RiskLevel.HIGH]),
            MatchRelation.INCOMPARABLE,
        ),
        (RuleMatch(read_only=True), RuleMatch(), MatchRelation.BROADER),
        (RuleMatch(), RuleMatch(read_only=True), MatchRelation.NARROWER),
        (RuleMatch(read_only=True), RuleMatch(read_only=False), MatchRelation.INCOMPARABLE),
        (
            RuleMatch(tools=["a"], read_only=None),
            RuleMatch(tools=["a", "b"], read_only=True),
            MatchRelation.INCOMPARABLE,
        ),
    ],
)
def test_match_relation_risk_boolean_and_mixed_dimensions(
    baseline: RuleMatch,
    candidate: RuleMatch,
    expected: MatchRelation,
) -> None:
    assert match_relation(baseline, candidate) is expected


def _predicate_match(predicate: Predicate) -> RuleMatch:
    return RuleMatch(arguments=[predicate])


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            Predicate(path="amount", operator="less_than", value=100),
            Predicate(path="amount", operator="less_than_or_equal", value=100),
            MatchRelation.BROADER,
        ),
        (
            Predicate(path="amount", operator="less_than_or_equal", value=100),
            Predicate(path="amount", operator="less_than", value=100),
            MatchRelation.NARROWER,
        ),
        (
            Predicate(path="amount", operator="greater_than_or_equal", value=100),
            Predicate(path="amount", operator="greater_than_or_equal", value=50),
            MatchRelation.BROADER,
        ),
        (
            Predicate(path="amount", operator="greater_than_or_equal", value=100),
            Predicate(path="amount", operator="greater_than", value=100),
            MatchRelation.NARROWER,
        ),
        (
            Predicate(path="kind", operator="in", value=["a"]),
            Predicate(path="kind", operator="in", value=["a", "b"]),
            MatchRelation.BROADER,
        ),
        (
            Predicate(path="kind", operator="not_in", value=["a"]),
            Predicate(path="kind", operator="not_in", value=["a", "b"]),
            MatchRelation.NARROWER,
        ),
        (
            Predicate(path="target", operator="matches", value="tenant-a"),
            Predicate(path="target", operator="matches", value="tenant-*"),
            MatchRelation.BROADER,
        ),
        (
            Predicate(path="tenant", operator="equals", value="a"),
            Predicate(path="other", operator="equals", value="a"),
            MatchRelation.UNKNOWN,
        ),
        (
            Predicate(path="tenant", operator="equals", value="a"),
            Predicate(path="tenant", operator="equals", value="b"),
            MatchRelation.UNKNOWN,
        ),
        (
            Predicate(path="kind", operator="in", value="a"),
            Predicate(path="kind", operator="in", value="b"),
            MatchRelation.UNKNOWN,
        ),
    ],
)
def test_match_relation_changed_predicates(
    before: Predicate,
    after: Predicate,
    expected: MatchRelation,
) -> None:
    assert match_relation(_predicate_match(before), _predicate_match(after)) is expected


def test_predicate_addition_and_removal_have_monotone_relations() -> None:
    predicate = Predicate(path="tenant", operator="equals", value="alpha")
    constrained = RuleMatch(arguments=[predicate])
    unconstrained = RuleMatch()
    assert match_relation(constrained, unconstrained) is MatchRelation.BROADER
    assert match_relation(unconstrained, constrained) is MatchRelation.NARROWER


def test_multiple_changed_predicates_remain_unknown() -> None:
    baseline = RuleMatch(
        arguments=[
            Predicate(path="tenant", operator="equals", value="a"),
            Predicate(path="region", operator="equals", value="us"),
        ]
    )
    candidate = RuleMatch(
        arguments=[
            Predicate(path="tenant", operator="equals", value="b"),
            Predicate(path="region", operator="equals", value="eu"),
        ]
    )
    assert match_relation(baseline, candidate) is MatchRelation.UNKNOWN


def test_huge_numeric_bound_is_rejected_before_static_analysis() -> None:
    with pytest.raises(ValidationError, match="cannot be canonicalized"):
        Predicate(path="amount", operator="less_than", value=10**10_000)


def test_non_numeric_bound_fails_closed_as_unknown() -> None:
    baseline = _predicate_match(Predicate(path="amount", operator="less_than", value="100"))
    candidate = _predicate_match(Predicate(path="amount", operator="less_than", value="200"))
    assert match_relation(baseline, candidate) is MatchRelation.UNKNOWN


@pytest.mark.parametrize(
    ("before_effect", "after_effect", "before_tools", "after_tools", "expected_kind"),
    [
        (
            DecisionEffect.DENY,
            DecisionEffect.ALLOW,
            ["payments.refund"],
            ["payments.refund"],
            AuthorityFindingKind.POTENTIAL_EXPANSION,
        ),
        (
            DecisionEffect.DENY,
            DecisionEffect.ALLOW,
            ["payments.refund"],
            ["billing.refund"],
            AuthorityFindingKind.UNKNOWN,
        ),
        (
            DecisionEffect.ALLOW,
            DecisionEffect.REQUIRE_APPROVAL,
            ["payments.refund"],
            ["payments.*"],
            AuthorityFindingKind.UNKNOWN,
        ),
        (
            DecisionEffect.REQUIRE_APPROVAL,
            DecisionEffect.DENY,
            ["payments.*"],
            ["payments.refund"],
            AuthorityFindingKind.UNKNOWN,
        ),
        (
            DecisionEffect.REQUIRE_APPROVAL,
            DecisionEffect.REQUIRE_APPROVAL,
            ["payments.refund"],
            ["payments.*"],
            AuthorityFindingKind.UNKNOWN,
        ),
    ],
)
def test_effect_and_scope_combinations_that_require_findings(
    before_effect: DecisionEffect,
    after_effect: DecisionEffect,
    before_tools: list[str],
    after_tools: list[str],
    expected_kind: AuthorityFindingKind,
) -> None:
    finding = _only_finding(
        _policy(_rule(effect=before_effect, tools=before_tools)),
        _policy(_rule(effect=after_effect, tools=after_tools)),
    )
    assert finding.kind is expected_kind


@pytest.mark.parametrize(
    ("before_effect", "after_effect", "before_tools", "after_tools"),
    [
        (
            DecisionEffect.ALLOW,
            DecisionEffect.DENY,
            ["payments.refund"],
            ["payments.*"],
        ),
        (
            DecisionEffect.ALLOW,
            DecisionEffect.REQUIRE_APPROVAL,
            ["payments.refund"],
            ["payments.refund"],
        ),
        (
            DecisionEffect.REQUIRE_APPROVAL,
            DecisionEffect.DENY,
            ["payments.refund"],
            ["payments.*"],
        ),
        (
            DecisionEffect.DENY,
            DecisionEffect.DENY,
            ["payments.refund"],
            ["payments.*"],
        ),
    ],
)
def test_provable_restrictions_do_not_create_static_findings(
    before_effect: DecisionEffect,
    after_effect: DecisionEffect,
    before_tools: list[str],
    after_tools: list[str],
) -> None:
    assert (
        analyze_authority_changes(
            _policy(_rule(effect=before_effect, tools=before_tools)),
            _policy(_rule(effect=after_effect, tools=after_tools)),
        )
        == []
    )


def test_added_allow_and_removed_deny_are_conservative_expansion_findings() -> None:
    added = _only_finding(_policy(), _policy(_rule(effect=DecisionEffect.ALLOW)))
    assert added.code == "rule_added"
    assert added.kind is AuthorityFindingKind.POTENTIAL_EXPANSION

    removed = _only_finding(
        _policy(_rule(effect=DecisionEffect.DENY)),
        _policy(),
    )
    assert removed.code == "rule_removed"
    assert removed.kind is AuthorityFindingKind.POTENTIAL_EXPANSION


def test_added_deny_and_removed_allow_cannot_increase_authority() -> None:
    assert (
        analyze_authority_changes(
            _policy(),
            _policy(_rule(effect=DecisionEffect.DENY)),
        )
        == []
    )
    assert (
        analyze_authority_changes(
            _policy(_rule(effect=DecisionEffect.ALLOW)),
            _policy(),
        )
        == []
    )


def test_default_relaxation_is_static_expansion() -> None:
    finding = _only_finding(
        _policy(default=DecisionEffect.DENY),
        _policy(default=DecisionEffect.REQUIRE_APPROVAL),
    )
    assert finding.code == "default_effect_relaxed"
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
