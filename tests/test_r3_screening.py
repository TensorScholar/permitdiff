from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.discover_r3_benchmark_candidates import selection_key, transition_id
from scripts.screen_r3_public_benchmark_candidates import (
    ScreeningError,
    apply_screening,
    prepare_screening,
)

SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "r3-screening-decisions.schema.json"


def _transition(
    *,
    baseline: str = "a" * 40,
    candidate: str = "b" * 40,
    status: str = "pending",
    reasons: list[str] | None = None,
    manual_review_required: bool | None = None,
) -> dict[str, object]:
    repository_url = "https://github.com/public/example"
    path = ".claude/settings.json"
    if manual_review_required is None:
        manual_review_required = status == "pending"
    return {
        "transition_id": transition_id(repository_url, baseline, candidate, path),
        "discovered_by": [{"query_id": "q1", "candidate_path": path}],
        "repository_full_name": "public/example",
        "repository_url": repository_url,
        "path": path,
        "baseline_commit": baseline,
        "candidate_commit": candidate,
        "baseline_blob": "c" * 40,
        "candidate_blob": "d" * 40,
        "baseline_sha256": "e" * 64,
        "candidate_sha256": "f" * 64,
        "baseline_size_bytes": 10,
        "candidate_size_bytes": 12,
        "candidate_commit_timestamp": "2026-09-01T00:00:00Z",
        "candidate_parent_count": 1,
        "permissions_changed": True,
        "screening_status": status,
        "exclusion_reasons": [] if reasons is None else reasons,
        "contamination_status": "clean",
        "selection_key": selection_key(repository_url, baseline, candidate, path),
        "manual_review_required": manual_review_required,
    }


def _ledger(*transitions: dict[str, object], complete: bool = True) -> dict[str, object]:
    return {
        "schema_version": "permitdiff.dev/r3-discovery-ledger/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "generated_at": "2026-09-01T00:00:00Z",
        "source": "github-rest-code-search-and-commit-history",
        "discovery_complete": complete,
        "limitations": ["test"],
        "queries": [],
        "discovered_location_count": 1,
        "transition_count": len(transitions),
        "transitions": list(transitions),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_prepare_screening_binds_exact_ledger_and_only_emits_pending(tmp_path) -> None:
    pending = _transition()
    excluded = _transition(
        baseline="1" * 40,
        candidate="2" * 40,
        status="excluded",
        reasons=["artifact_parse_failure"],
    )
    ledger_path = tmp_path / "ledger.json"
    _write_json(ledger_path, _ledger(pending, excluded))

    worksheet = prepare_screening(ledger_path)

    assert worksheet["schema_version"] == "permitdiff.dev/r3-screening-decisions/v1"
    assert len(worksheet["decisions"]) == 1
    decision = worksheet["decisions"][0]
    assert decision["transition_id"] == pending["transition_id"]
    assert decision["decision"] == "pending"
    assert decision["rationale"] is None
    assert decision["reviewer"] is None


def test_apply_screening_can_mark_pending_transition_eligible(tmp_path) -> None:
    source = _transition()
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(source))

    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    decision["decision"] = "eligible"
    decision["rationale"] = "Public project-scoped authorization change with sufficient semantics."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)

    screened = apply_screening(ledger_path, decisions_path, SCHEMA)

    resolved = screened["transitions"][0]
    assert resolved["screening_status"] == "eligible"
    assert resolved["exclusion_reasons"] == []
    assert resolved["manual_review_required"] is False
    assert resolved["selection_key"] == source["selection_key"]


def test_apply_screening_preserves_fixed_exclusion_reason(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(_transition()))

    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    decision["decision"] = "excluded"
    decision["exclusion_reasons"] = ["insufficient_public_semantics"]
    decision["rationale"] = "Public documentation is insufficient for output-blind review."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)

    screened = apply_screening(ledger_path, decisions_path, SCHEMA)

    resolved = screened["transitions"][0]
    assert resolved["screening_status"] == "excluded"
    assert resolved["exclusion_reasons"] == ["insufficient_public_semantics"]
    assert resolved["manual_review_required"] is False


def test_apply_screening_rejects_missing_manual_decision(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(_transition()))

    worksheet = prepare_screening(ledger_path)
    worksheet["decisions"] = []
    _write_json(decisions_path, worksheet)

    with pytest.raises(ScreeningError, match="missing pending transitions"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_apply_screening_rejects_tampered_transition_metadata(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(_transition()))

    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    decision["decision"] = "eligible"
    decision["repository_url"] = "https://github.com/public/other"
    decision["rationale"] = "Attempted target substitution."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)

    with pytest.raises(ScreeningError, match="metadata mismatch"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_apply_screening_rejects_non_preregistered_exclusion(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(_transition()))

    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    decision["decision"] = "excluded"
    decision["exclusion_reasons"] = ["product_did_not_like_it"]
    decision["rationale"] = "This reason is intentionally invalid."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)

    with pytest.raises(ScreeningError, match="schema validation failed"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_prepare_screening_rejects_incomplete_discovery_frame(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    _write_json(ledger_path, _ledger(_transition(), complete=False))

    with pytest.raises(ScreeningError, match="complete discovery ledger"):
        prepare_screening(ledger_path)


def test_apply_screening_rejects_eligible_case_without_artifact_provenance(tmp_path) -> None:
    transition = _transition()
    transition["baseline_sha256"] = None
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(transition))

    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    decision["decision"] = "eligible"
    decision["rationale"] = "Would otherwise be eligible."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)

    with pytest.raises(ScreeningError, match="lacks immutable artifact provenance"):
        apply_screening(ledger_path, decisions_path, SCHEMA)
