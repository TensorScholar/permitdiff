from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from scripts.r3_documentation_snapshots import (
    DocumentationSnapshotError,
    documentation_set_digest,
    validate_manifest,
)
from scripts.r3_execution_environment import EnvironmentLockError, validate_environment_snapshot
from scripts.r3_pre_discovery_contract import (
    PreDiscoveryContractError,
    natural_corpus_disposition,
    selected_case_failure_disposition,
    validate_selection_shape,
)
from scripts.r3_review_assignment import build_assignment, validate_balance
from scripts.r3_study_results import (
    StudyResultError,
    canonical_rate,
    derive_top_level_outcome,
    linear_quantile,
    summarize_timing,
    validate_rate,
    validate_terminal_completeness,
)

ROOT = Path(__file__).resolve().parents[1]


def _json(path: str) -> dict[str, object]:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_new_schemas_are_valid_draft_2020_12() -> None:
    paths = [
        "docs/r3-condition-assignment.schema.json",
        "docs/r3-documentation-snapshot-manifest.schema.json",
        "docs/r3-execution-environment-lock.schema.json",
        "docs/r3-pre-discovery-hardening-contract.schema.json",
        "docs/r3-pre-execution-lock-v3.schema.json",
        "docs/r3-reviewer-protocol.schema.json",
        "docs/r3-reviewer-roster.schema.json",
        "docs/r3-study-result-set.schema.json",
        "docs/r3-freeze-completion-records-v2.schema.json",
    ]
    for path in paths:
        Draft202012Validator.check_schema(_json(path))


def test_hardening_contract_preserves_research_boundary() -> None:
    contract = _json("validation/r3-benchmark/exploratory/pre-discovery-hardening-contract-v1.json")
    assert contract["adopted_against_main"] == "c3f3a866333f75ae3a1668177cda37c68aa05409"
    assert contract["adopted_before_public_discovery"] is True
    assert contract["hard_boundaries"] == {
        "canonical_r3_results": "NOT_CREATED",
        "empirical_scientific_validation_percent": 0,
        "external_validation_claim": "NOT_ESTABLISHED",
        "r3_execution": "NOT_STARTED",
    }


@pytest.mark.parametrize(
    ("eligible", "expected"),
    [
        (0, "ABORT_CONSTRUCTION_PROTOCOL_AMENDMENT_REQUIRED"),
        (11, "ABORT_CONSTRUCTION_PROTOCOL_AMENDMENT_REQUIRED"),
        (12, "SELECT_ALL_ELIGIBLE_AND_REPORT_PREDECLARED_SHORTFALL"),
        (17, "SELECT_ALL_ELIGIBLE_AND_REPORT_PREDECLARED_SHORTFALL"),
        (18, "SELECT_EXACTLY_TARGET"),
        (25, "SELECT_EXACTLY_TARGET"),
    ],
)
def test_natural_corpus_thresholds_are_deterministic(eligible: int, expected: str) -> None:
    assert natural_corpus_disposition(eligible) == expected


def test_selection_below_minimum_fails_closed() -> None:
    selection = {
        "target_cases": 18,
        "max_cases_per_repository": 2,
        "eligible_case_count": 11,
        "selected_case_count": 11,
        "shortfall": 7,
    }
    with pytest.raises(PreDiscoveryContractError, match="below frozen minimum"):
        validate_selection_shape(selection)


def test_selected_case_failure_never_replaces() -> None:
    assert (
        selected_case_failure_disposition("BROKEN_MATERIALIZATION")
        == "ABORT_CURRENT_CORPUS_VERSION_NO_REPLACEMENT"
    )


def test_condition_assignment_is_reproducible_and_balanced() -> None:
    manifest = {"cases": [{"id": f"case-{index}"} for index in range(12)]}
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    roster = {
        "participants": [
            {
                "participant_id": participant,
                "domain_familiarity_attested": True,
                "claude_settings_familiarity_attested": True,
                "training_completed": True,
                "training_protocol_version": "r3-reviewer-training-v1",
                "product_behavior_contributor": False,
                "methodology_only_contributor": False,
                "disqualifying_conflict": False,
                "case_specific_prior_exposure_case_ids": [],
                "case_specific_adjudication_case_ids": [],
            }
            for participant in ("p1", "p2", "p3")
        ]
    }
    roster_bytes = json.dumps(roster, sort_keys=True).encode()
    protocol_bytes = b'{"protocol_version":"r3-reviewer-protocol-v1"}'
    first = build_assignment(
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        roster=roster,
        roster_bytes=roster_bytes,
        reviewer_protocol_bytes=protocol_bytes,
    )
    second = build_assignment(
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        roster=roster,
        roster_bytes=roster_bytes,
        reviewer_protocol_bytes=protocol_bytes,
    )
    assert first == second
    validate_balance(first)
    assert len(first["assignments"]) == 36


def test_condition_assignment_rejects_case_specific_exposure() -> None:
    manifest = {"cases": [{"id": "case-1"}]}
    roster = {
        "participants": [
            {
                "participant_id": participant,
                "domain_familiarity_attested": True,
                "claude_settings_familiarity_attested": True,
                "training_completed": True,
                "training_protocol_version": "r3-reviewer-training-v1",
                "product_behavior_contributor": False,
                "methodology_only_contributor": False,
                "disqualifying_conflict": False,
                "case_specific_prior_exposure_case_ids": ["case-1"] if participant == "p1" else [],
                "case_specific_adjudication_case_ids": [],
            }
            for participant in ("p1", "p2", "p3")
        ]
    }
    with pytest.raises(ValueError, match="case-specific exposure"):
        build_assignment(
            manifest=manifest,
            manifest_bytes=json.dumps(manifest).encode(),
            roster=roster,
            roster_bytes=json.dumps(roster).encode(),
            reviewer_protocol_bytes=b"reviewer-protocol",
        )


def test_documentation_snapshots_are_content_addressed(tmp_path: Path) -> None:
    content = b"frozen documentation\n"
    snapshot = tmp_path / "docs" / "permission.md"
    snapshot.parent.mkdir()
    snapshot.write_bytes(content)
    doc = {
        "document_id": "claude-permissions",
        "source_url": "https://example.com/permissions",
        "retrieved_at": "2026-09-14T00:00:00Z",
        "snapshot_path": "docs/permission.md",
        "snapshot_sha256": _sha(content),
        "content_type": "text/markdown",
        "format": "markdown",
        "normalization": "none",
    }
    case = {
        "case_id": "case-1",
        "documentation_ids": ["claude-permissions"],
        "documentation_snapshot_set_sha256": documentation_set_digest([doc]),
    }
    manifest = {
        "schema_version": "permitdiff.dev/r3-documentation-snapshot-manifest/v1",
        "manifest_version": "r3-documentation-snapshots-v1",
        "corpus_id": "corpus-v1",
        "generated_at": "2026-09-14T00:00:00Z",
        "documents": [doc],
        "cases": [case],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = validate_manifest(
        manifest_path,
        schema_path=ROOT / "docs/r3-documentation-snapshot-manifest.schema.json",
        expected_case_ids=["case-1"],
    )
    assert result["document_count"] == 1
    snapshot.write_bytes(b"mutated\n")
    with pytest.raises(DocumentationSnapshotError, match="hash mismatch"):
        validate_manifest(
            manifest_path,
            schema_path=ROOT / "docs/r3-documentation-snapshot-manifest.schema.json",
        )


def test_execution_environment_drift_fails_closed() -> None:
    lock = _json("validation/r3-benchmark/exploratory/permitdiff-execution-environment-v1.json")
    packages = dict(lock["runtime_dependencies"])
    snapshot = {
        "python_version": "3.13.15",
        "os": "linux",
        "architecture": "amd64",
        "timezone": "UTC",
        "encoding": "utf-8",
        "packages": packages,
    }
    validate_environment_snapshot(lock, snapshot)
    snapshot["architecture"] = "arm64"
    with pytest.raises(EnvironmentLockError, match="architecture drift"):
        validate_environment_snapshot(lock, snapshot)


def test_canonical_rate_rejects_impossible_arithmetic() -> None:
    assert canonical_rate(0, 0) == {"numerator": 0, "denominator": 0, "rate": None}
    assert canonical_rate(1, 4)["rate"] == 0.25
    with pytest.raises(StudyResultError, match="cannot exceed"):
        canonical_rate(2, 1)
    with pytest.raises(StudyResultError, match="canonical arithmetic"):
        validate_rate({"numerator": 1, "denominator": 4, "rate": 0.5})


def test_timing_uses_frozen_linear_quartiles() -> None:
    assert linear_quantile([10], 0.25) == 10
    summary = summarize_timing([10, 20, 30, 40])
    assert summary == {
        "timing_valid_case_count": 4,
        "q1_active_seconds": 17.5,
        "median_active_seconds": 25.0,
        "q3_active_seconds": 32.5,
        "iqr_active_seconds": 15.0,
        "total_active_seconds": 100.0,
    }
    assert summarize_timing([])["median_active_seconds"] is None


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"invalidated": True}, "INVALIDATED"),
        ({"automatic_pass_error_count": 1}, "SAFETY_FAILURE"),
        (
            {
                "assisted_missed": 0,
                "manual_missed": 1,
                "permitdiff_recall": 1.0,
                "simple_baseline_recall": 0.5,
            },
            "SUPPORTED",
        ),
        (
            {
                "assisted_missed": 1,
                "manual_missed": 1,
                "timing_complete": True,
                "assisted_median_seconds": 60.0,
                "manual_median_seconds": 100.0,
                "assisted_total_seconds": 600.0,
                "manual_total_seconds": 1000.0,
            },
            "EFFORT_ADVANTAGE_ONLY",
        ),
        (
            {
                "assisted_missed": 1,
                "manual_missed": 1,
                "timing_complete": True,
                "assisted_median_seconds": 95.0,
                "manual_median_seconds": 100.0,
                "assisted_total_seconds": 950.0,
                "manual_total_seconds": 1000.0,
            },
            "NO_MEANINGFUL_ADVANTAGE",
        ),
        ({"permitdiff_escalation_burden": 0.5}, "MIXED_INCONCLUSIVE"),
    ],
)
def test_interpretation_precedence_is_deterministic(
    kwargs: dict[str, object], expected: str
) -> None:
    values: dict[str, object] = {
        "invalidated": False,
        "automatic_pass_error_count": 0,
        "permitdiff_escalation_burden": 0.1,
        "assisted_missed": 1,
        "manual_missed": 1,
        "assisted_false_alerts": 0,
        "manual_false_alerts": 0,
        "permitdiff_recall": 0.8,
        "simple_baseline_recall": 0.5,
        "assisted_escalations": 0,
        "manual_escalations": 0,
        "timing_complete": False,
        "assisted_median_seconds": None,
        "manual_median_seconds": None,
        "assisted_total_seconds": None,
        "manual_total_seconds": None,
    }
    values.update(kwargs)
    outcome, _ = derive_top_level_outcome(**values)  # type: ignore[arg-type]
    assert outcome == expected


def test_terminal_completeness_requires_every_locked_case_and_condition() -> None:
    cases = ["case-1", "case-2"]
    conditions = (
        "PERMITDIFF_MACHINE",
        "SIMPLE_AUTOMATED_BASELINE",
        "PERMITDIFF_ASSISTED",
        "STRUCTURED_MANUAL",
        "SOURCE_TEXT_DIFF",
    )
    result_set = {
        "terminal_states": [
            {"case_id": case_id, "condition": condition, "state": "RECORDED"}
            for case_id in cases
            for condition in conditions
        ]
    }
    validate_terminal_completeness(result_set, cases)
    result_set["terminal_states"].pop()
    with pytest.raises(StudyResultError, match="population mismatch"):
        validate_terminal_completeness(result_set, cases)


def test_frozen_selection_target_and_cap_rejected_when_non_default() -> None:
    base = {
        "target_cases": 18,
        "max_cases_per_repository": 2,
        "eligible_case_count": 18,
        "selected_case_count": 18,
        "shortfall": 0,
    }
    bad_target = dict(base, target_cases=17)
    with pytest.raises(
        PreDiscoveryContractError, match="target case count must remain exactly 18"
    ):
        validate_selection_shape(bad_target)
    bad_cap = dict(base, max_cases_per_repository=3)
    with pytest.raises(
        PreDiscoveryContractError, match="per-repository cap must remain exactly 2"
    ):
        validate_selection_shape(bad_cap)


def test_minimum_threshold_selection_shape() -> None:
    at_minimum = {
        "target_cases": 18,
        "max_cases_per_repository": 2,
        "eligible_case_count": 12,
        "selected_case_count": 12,
        "shortfall": 6,
    }
    assert (
        validate_selection_shape(at_minimum)
        == "SELECT_ALL_ELIGIBLE_AND_REPORT_PREDECLARED_SHORTFALL"
    )
    at_target = {
        "target_cases": 18,
        "max_cases_per_repository": 2,
        "eligible_case_count": 18,
        "selected_case_count": 18,
        "shortfall": 0,
    }
    assert validate_selection_shape(at_target) == "SELECT_EXACTLY_TARGET"
