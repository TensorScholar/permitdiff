from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from permitdiff.errors import PolicyLoadError
from permitdiff.models import DecisionEffect
from permitdiff.policy import PolicyDocument, PolicyRule, Predicate, RuleMatch


def test_policy_loads_and_defaults_to_deny(baseline: PolicyDocument) -> None:
    assert baseline.default_effect is DecisionEffect.DENY
    assert baseline.metadata.version == "1.0.0"


def test_policy_digest_is_stable(baseline: PolicyDocument) -> None:
    assert baseline.digest() == baseline.model_copy().digest()
    assert len(baseline.digest()) == 64


def test_duplicate_rule_ids_are_rejected(baseline: PolicyDocument) -> None:
    raw = baseline.model_dump(mode="json")
    raw["rules"].append(raw["rules"][0])
    with pytest.raises(ValidationError, match="rule ids must be unique"):
        PolicyDocument.model_validate(raw)


def test_unknown_fields_fail_closed(tmp_path: Path) -> None:
    policy = tmp_path / "bad.yaml"
    policy.write_text(
        """api_version: permitdiff.dev/v1alpha1
kind: Policy
metadata: {name: x, version: 1}
default_effect: deny
rules: []
unknown: true
""",
        encoding="utf-8",
    )
    with pytest.raises(PolicyLoadError, match="unknown"):
        PolicyDocument.from_yaml(policy)


def test_non_mapping_root_is_rejected(tmp_path: Path) -> None:
    policy = tmp_path / "bad.yaml"
    policy.write_text("- not\n- a\n- policy\n", encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="root must be a mapping"):
        PolicyDocument.from_yaml(policy)


def test_missing_policy_is_wrapped(tmp_path: Path) -> None:
    with pytest.raises(PolicyLoadError, match="failed to load policy"):
        PolicyDocument.from_yaml(tmp_path / "missing.yaml")


def test_exists_requires_boolean() -> None:
    with pytest.raises(ValidationError, match="requires a boolean"):
        Predicate(path="x", operator="exists", value="yes")


def test_matches_requires_strings() -> None:
    with pytest.raises(ValidationError, match="glob patterns"):
        Predicate(path="x", operator="matches", value=["a*", 1])


def test_allow_rule_requires_explicit_annotation_trust() -> None:
    with pytest.raises(ValidationError, match="security_metadata_trusted"):
        PolicyRule(
            id="unsafe-read",
            description="Unsafe implicit trust.",
            effect=DecisionEffect.ALLOW,
            match=RuleMatch(read_only=True),
        )


def test_allow_rule_without_annotations_remains_valid() -> None:
    rule = PolicyRule(
        id="explicit-tool",
        description="A tool identity can be explicitly allowed.",
        effect=DecisionEffect.ALLOW,
        match=RuleMatch(tools=["internal.health"]),
    )
    assert rule.effect is DecisionEffect.ALLOW


def test_predicate_value_must_be_json_compatible() -> None:
    with pytest.raises(ValidationError, match="non-JSON"):
        Predicate(path="x", operator="equals", value={"not-json"})


def test_glob_lists_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        RuleMatch(tools=[])
