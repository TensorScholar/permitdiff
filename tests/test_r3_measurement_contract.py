from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT / "validation" / "r3-benchmark" / "exploratory" / "measurement-contract-v2.json"
)
SCHEMA_PATH = ROOT / "docs" / "r3-measurement-contract.schema.json"


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_measurement_contract_v2_freezes_review_trigger_and_scoring_matrix() -> None:
    contract = _load(CONTRACT_PATH)
    schema = _load(SCHEMA_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(contract)

    scoring = contract["review_trigger_scoring_contract"]
    assert isinstance(scoring, dict)
    assert scoring["version"] == "r3-review-trigger-scoring-v1"

    relation_policy = scoring["relation_trigger_policy"]
    assert relation_policy == {
        "WIDENING": "REQUIRES_AUTHORIZATION_REVIEW",
        "MIXED": "REQUIRES_AUTHORIZATION_REVIEW",
        "RESTRICTIVE": "NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE",
        "EQUIVALENT": "NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE",
        "UNRESOLVED": "REQUIRES_SEMANTIC_ESCALATION",
    }

    classes = scoring["ground_truth_review_classes"]
    assert classes["known_review_required_relations"] == ["WIDENING", "MIXED"]
    assert classes["known_no_review_by_direction_relations"] == [
        "RESTRICTIVE",
        "EQUIVALENT",
    ]
    assert classes["uncertain_relations"] == ["UNRESOLVED"]


def test_known_widening_stays_positive_when_tool_is_unsupported() -> None:
    contract = _load(CONTRACT_PATH)
    scoring = contract["review_trigger_scoring_contract"]
    assert isinstance(scoring, dict)

    independence = scoring["dimension_independence"]
    assert independence[
        "unsupported_known_review_required_case_remains_in_overall_positive_denominator"
    ] is True
    assert independence["tool_support_can_change_source_semantic_relation"] is False

    subset = scoring["supported_subset_reporting"]
    assert subset["overall_known_review_required_denominator_includes"] == [
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "UNSUPPORTED",
    ]
    assert subset["secondary_view_only"] is True
    assert subset["must_not_replace_overall_metrics"] is True


def test_uncertainty_only_block_is_escalation_not_detection() -> None:
    contract = _load(CONTRACT_PATH)
    scoring = contract["review_trigger_scoring_contract"]
    assert isinstance(scoring, dict)

    independence = scoring["dimension_independence"]
    assert independence["uncertainty_only_gate_block_counts_as_definite_detection"] is False

    unresolved = scoring["unresolved_policy"]
    assert unresolved["ordinary_positive"] is False
    assert unresolved["ordinary_negative"] is False
    assert unresolved["requires_semantic_escalation"] is True
    assert unresolved["included_in_directional_detection_error_denominators"] is False

    metrics = scoring["metric_definitions"]
    assert metrics["definite_detection_recall"]["escalation_counts_as_detection"] is False


def test_metric_denominators_are_predeclared_and_non_circular() -> None:
    contract = _load(CONTRACT_PATH)
    scoring = contract["review_trigger_scoring_contract"]
    assert isinstance(scoring, dict)
    metrics = scoring["metric_definitions"]

    assert metrics["definite_detection_recall"]["denominator"] == (
        "known_review_required_relations"
    )
    assert metrics["automatic_pass_error_rate"]["denominator"] == (
        "known_review_required_relations"
    )
    assert metrics["false_alarm_burden"]["denominator"] == (
        "known_no_review_by_direction_relations"
    )
    assert metrics["support_boundary_rate"]["numerator_tool_support"] == [
        "PARTIALLY_SUPPORTED",
        "UNSUPPORTED",
    ]

    reporting = scoring["rate_reporting"]
    assert reporting["report_numerator_and_denominator"] is True
    assert reporting["zero_denominator_rate"] is None
    assert reporting["no_post_outcome_rule_changes"] is True


def test_schema_rejects_post_hoc_scoring_rule_mutation() -> None:
    contract = _load(CONTRACT_PATH)
    schema = _load(SCHEMA_PATH)
    mutated = copy.deepcopy(contract)
    scoring = mutated["review_trigger_scoring_contract"]
    assert isinstance(scoring, dict)
    relation_policy = scoring["relation_trigger_policy"]
    assert isinstance(relation_policy, dict)
    relation_policy["UNRESOLVED"] = "NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE"

    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(mutated)
