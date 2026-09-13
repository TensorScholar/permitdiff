from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT / "validation" / "r3-benchmark" / "exploratory" / "freeze-completion-contract-v1.json"
)
CONTRACT_SCHEMA_PATH = ROOT / "docs" / "r3-freeze-completion-contract.schema.json"
RECORDS_SCHEMA_PATH = ROOT / "docs" / "r3-freeze-completion-records.schema.json"


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_baseline_module() -> ModuleType:
    path = ROOT / "scripts" / "r3_simple_native_baseline.py"
    spec = importlib.util.spec_from_file_location("r3_simple_native_baseline", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_completion_contract_and_schemas_are_valid() -> None:
    contract = _load(CONTRACT_PATH)
    schema = _load(CONTRACT_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(contract)
    records_schema = _load(RECORDS_SCHEMA_PATH)
    Draft202012Validator.check_schema(records_schema)


def test_records_schema_resolves_nested_result_definitions() -> None:
    records_schema = _load(RECORDS_SCHEMA_PATH)
    validator = Draft202012Validator(records_schema)
    digest = "a" * 64
    rate = {"numerator": 0, "denominator": 1, "rate": 0.0}

    validator.validate(
        {
            "schema_version": "permitdiff.dev/r3-permitdiff-result-record/v1",
            "case_id": "case-1",
            "product_commit": "1f3b3a4afda67c01c4f29a93a45b18511980036b",
            "execution_state": "EXECUTED",
            "scenario_channel_state": "PRESENT",
            "product_disposition": "DEFINITE_REVIEW_REQUIRED",
            "command_argv": ["python", "-m", "permitdiff"],
            "report_artifact": {"path": "report.json", "sha256": digest},
            "projection_evidence_artifact": {
                "path": "projection-evidence.json",
                "sha256": digest,
            },
            "exit_code": 1,
            "runtime_seconds": 0.1,
            "error": None,
        }
    )

    validator.validate(
        {
            "schema_version": "permitdiff.dev/r3-comparative-analysis-result/v1",
            "corpus_id": "corpus-1",
            "pre_execution_lock_sha256": digest,
            "primary_population": "public_historical_natural_only",
            "natural_case_count": 1,
            "invalidated_case_count": 0,
            "permitdiff": {
                "definite_detection_recall": rate,
                "automatic_pass_error_rate": rate,
                "decisive_coverage": rate,
                "escalation_burden": rate,
                "false_alarm_burden": rate,
            },
            "permitdiff_assisted": {
                "missed_consequential_changes": 0,
                "false_or_misleading_alerts": 0,
                "escalation_count": 0,
                "agreement_with_reference": rate,
                "timing_valid_case_count": 1,
                "median_active_seconds": 10.0,
                "total_active_seconds": 10.0,
            },
            "structured_manual": {
                "missed_consequential_changes": 0,
                "false_or_misleading_alerts": 0,
                "escalation_count": 0,
                "agreement_with_reference": rate,
                "timing_valid_case_count": 1,
                "median_active_seconds": 20.0,
                "total_active_seconds": 20.0,
            },
            "simple_automated_baseline": {
                "review_trigger_recall": rate,
                "false_alarm_burden": rate,
                "unknown_or_error_burden": rate,
            },
            "top_level_outcome": "EFFORT_ADVANTAGE_ONLY",
            "interpretation_rule_version": "r3-primary-interpretation-v1",
        }
    )


def test_primary_inference_and_severity_cannot_be_rescued_post_hoc() -> None:
    contract = _load(CONTRACT_PATH)
    primary = contract["primary_inference_boundary"]
    assert isinstance(primary, dict)
    assert primary["primary_slice"] == "public_historical_natural"
    assert primary["synthetic_or_stress_is_secondary_only"] is True
    assert primary["synthetic_or_stress_cannot_rescue_primary_result"] is True

    severity = contract["severity_policy"]
    assert isinstance(severity, dict)
    assert severity["approach"] == "B_DESCRIPTIVE_NON_PRIMARY_ONLY"
    assert "top_level_interpretation" in severity["forbidden_uses"]


def test_primary_human_conditions_have_evidence_parity_except_permitdiff_output() -> None:
    contract = _load(CONTRACT_PATH)
    matrix = contract["evidence_access_matrix"]
    assert isinstance(matrix, dict)
    conditions = matrix["conditions"]
    assert isinstance(conditions, dict)
    assisted = dict(conditions["permitdiff_assisted_human"])
    manual = dict(conditions["structured_manual"])

    assisted.pop("permitdiff_machine_output")
    assisted.pop("permitdiff_projection_evidence")
    manual.pop("permitdiff_machine_output")
    manual.pop("permitdiff_projection_evidence")
    assert assisted == manual


def test_scenario_absence_is_escalation_not_fabricated_execution() -> None:
    contract = _load(CONTRACT_PATH)
    execution = contract["permitdiff_execution"]
    assert isinstance(execution, dict)
    absent = execution["scenario_absent_behavior"]
    assert isinstance(absent, dict)
    assert absent["run_product_command"] is False
    assert absent["product_disposition"] == "ESCALATE"
    assert absent["case_remains_in_denominators"] is True
    assert absent["fabricated_or_answer_informed_scenario_forbidden"] is True


def test_interpretation_precedence_blocks_metric_shopping() -> None:
    contract = _load(CONTRACT_PATH)
    interpretation = contract["top_level_interpretation"]
    assert isinstance(interpretation, dict)
    assert interpretation["precedence"] == [
        "INVALIDATED",
        "SAFETY_FAILURE",
        "SUPPORTED",
        "EFFORT_ADVANTAGE_ONLY",
        "NO_MEANINGFUL_ADVANTAGE",
        "MIXED_INCONCLUSIVE",
    ]
    assert interpretation["result_selection_from_secondary_slices_forbidden"] is True
    assert interpretation["post_result_rule_changes_forbidden"] is True


def test_simple_baseline_flags_new_allow_and_ask_deny_changes(tmp_path: Path) -> None:
    module = _load_baseline_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(
            {
                "permissions": {
                    "defaultMode": "dontAsk",
                    "allow": ["Read"],
                    "ask": [],
                    "deny": [],
                }
            }
        ),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(
            {
                "permissions": {
                    "defaultMode": "dontAsk",
                    "allow": ["Read", "Bash(git status)"],
                    "ask": [],
                    "deny": [],
                }
            }
        ),
        encoding="utf-8",
    )

    result = module.evaluate("case-1", baseline, candidate)
    assert result["disposition"] == "REVIEW_REQUIRED"
    assert result["added_allow"] == ["Bash(git status)"]


def test_simple_baseline_reports_removal_only_as_no_review(tmp_path: Path) -> None:
    module = _load_baseline_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps(
            {
                "permissions": {
                    "defaultMode": "dontAsk",
                    "allow": ["Read", "Write"],
                    "ask": [],
                    "deny": [],
                }
            }
        ),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps(
            {
                "permissions": {
                    "defaultMode": "dontAsk",
                    "allow": ["Read"],
                    "ask": [],
                    "deny": [],
                }
            }
        ),
        encoding="utf-8",
    )

    result = module.evaluate("case-2", baseline, candidate)
    assert result["disposition"] == "NO_REVIEW_REQUIRED"
    assert result["removed_allow"] == ["Write"]


def test_simple_baseline_returns_unknown_outside_frozen_mode(tmp_path: Path) -> None:
    module = _load_baseline_module()
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps({"permissions": {"defaultMode": "default", "allow": []}}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"permissions": {"defaultMode": "dontAsk", "allow": []}}),
        encoding="utf-8",
    )

    result = module.evaluate("case-3", baseline, candidate)
    assert result["disposition"] == "UNKNOWN"


def test_human_schema_rejects_permitdiff_visibility_in_manual_condition() -> None:
    records = _load(RECORDS_SCHEMA_PATH)
    defs = records["$defs"]
    assert isinstance(defs, dict)
    schema = defs["humanReviewRecord"]
    record = {
        "schema_version": "permitdiff.dev/r3-human-review-record/v1",
        "record_id": "r1",
        "case_id": "c1",
        "condition": "STRUCTURED_MANUAL",
        "participant_id": "p1",
        "order_index": 1,
        "started_at": "2026-09-13T12:00:00Z",
        "submitted_at": "2026-09-13T12:01:00Z",
        "active_seconds": 60,
        "timing_valid": True,
        "timing_invalid_reason": None,
        "decision": "NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE",
        "confidence": 4,
        "rationale": "frozen evidence supports restriction",
        "consulted_documentation_refs": ["doc-1"],
        "additional_documentation_consulted": False,
        "uncertainty_notes": None,
        "blinding_state": "OUTPUT_BLIND_GROUND_TRUTH",
        "permitdiff_output_visible": True,
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(record)


def test_freeze_completion_does_not_create_real_r3_corpus_or_results() -> None:
    exploratory = ROOT / "validation" / "r3-benchmark" / "exploratory"
    forbidden = [
        exploratory / "discovery-ledger.json",
        exploratory / "screening-decisions.json",
        exploratory / "screened-discovery-ledger.json",
        exploratory / "public-selection.json",
        exploratory / "public-historical-v1",
        exploratory / "review-context.json",
        exploratory / "review-packets-v2",
        exploratory / "adjudications-v2.json",
        exploratory / "scenario-channels-v1.json",
        exploratory / "results",
    ]
    assert all(not path.exists() for path in forbidden)
