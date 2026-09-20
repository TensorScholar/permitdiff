from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.r3_cb01_corpus_construction as cb01
from scripts.discover_r3_benchmark_candidates import selection_key, transition_id
from scripts.screen_r3_public_benchmark_candidates import (
    ScreeningError,
    apply_screening,
    prepare_screening,
)

SCHEMA = Path(__file__).resolve().parents[1] / "docs" / "r3-screening-decisions.schema.json"
ROOT = Path(__file__).resolve().parents[1]
CB01_CONTRACT_PATH = (
    ROOT
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)
_SYNTHETIC_STUDY_COMMIT = "2" * 40


def _load_contract() -> tuple[dict[str, Any], bytes]:
    raw_bytes = CB01_CONTRACT_PATH.read_bytes()
    contract = json.loads(raw_bytes)
    assert isinstance(contract, dict)
    return contract, raw_bytes


def _queries_from_contract(contract: dict[str, Any]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for entry in contract["search_frame"]:
        queries.append(
            {
                "query_id": entry["query_id"],
                "concept": entry["concept"],
                "candidate_path": entry["candidate_path"],
                "api_query": entry["api_query"],
                "reported_total_count": 0,
                "retrieved_count": 0,
                "exact_candidate_path_count": 0,
                "incomplete_results": False,
                "api_result_cap_reached": False,
            }
        )
    return queries


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
    contract, contract_bytes = _load_contract()
    return {
        "schema_version": "permitdiff.dev/r3-public-discovery-ledger/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "study_repository_commit": _SYNTHETIC_STUDY_COMMIT,
        "producer_id": "permitdiff-r3-canonical-public-discovery-v2",
        "generated_at": "2026-09-01T00:00:00Z",
        "source": "github-rest-code-search-and-commit-history",
        "discovery_complete": complete,
        "limitations": ["test"],
        "queries": _queries_from_contract(contract),
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


# ---------------------------------------------------------------------------
# Packet B3 — deterministic screened derivation (synthetic, no network)
# ---------------------------------------------------------------------------


def _eligible_worksheet(
    ledger_path: Path, decisions_path: Path
) -> tuple[dict[str, object], dict[str, object]]:
    _write_json(ledger_path, _ledger(_transition()))
    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    assert isinstance(decision, dict)
    decision["decision"] = "eligible"
    decision["rationale"] = "Public project-scoped authorization change."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert isinstance(ledger, dict)
    return ledger, worksheet


def test_b3_producer_output_equals_deterministic_derivation(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    ledger, worksheet = _eligible_worksheet(ledger_path, decisions_path)
    contract, contract_bytes = _load_contract()
    ledger_bytes = ledger_path.read_bytes()
    decisions_bytes = decisions_path.read_bytes()
    expected = cb01.derive_screened_ledger(
        ledger, ledger_bytes, worksheet, decisions_bytes, contract, contract_bytes
    )
    produced = apply_screening(ledger_path, decisions_path, SCHEMA)
    assert produced == expected
    assert produced["schema_version"] == "permitdiff.dev/r3-screened-discovery-ledger/v1"
    assert produced["study_repository_commit"] == _SYNTHETIC_STUDY_COMMIT
    assert produced["cb01_contract_version"] == "r3-cb01-corpus-construction-v1"


def test_b3_raw_byte_mutation_rejected(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _eligible_worksheet(ledger_path, decisions_path)
    mutated = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert isinstance(mutated, dict)
    mutated["discovered_location_count"] = 9999
    ledger_path.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ScreeningError, match=r"bound|match|bytes"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_b3_decision_byte_mutation_rejected(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _eligible_worksheet(ledger_path, decisions_path)
    raw_ledger_bytes = ledger_path.read_bytes()
    worksheet = json.loads(decisions_path.read_text(encoding="utf-8"))
    assert isinstance(worksheet, dict)
    worksheet["instructions"] = "Tampered instructions still bound to other bytes."
    decisions_path.write_text(json.dumps(worksheet, indent=2) + "\n", encoding="utf-8")
    # Rebind worksheet to the same ledger bytes is fine; tampering the ledger
    # binding itself must fail.
    worksheet["source_ledger_sha256"] = "0" * 64
    decisions_path.write_text(json.dumps(worksheet, indent=2) + "\n", encoding="utf-8")
    assert raw_ledger_bytes is not None
    with pytest.raises(ScreeningError, match=r"bound|sha256|match"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_b3_pending_extra_duplicate_decisions_rejected(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(_transition()))
    worksheet = prepare_screening(ledger_path)
    # Pending outcome.
    pending = copy.deepcopy(worksheet)
    assert isinstance(pending["decisions"], list)
    pending["decisions"][0]["decision"] = "pending"
    _write_json(decisions_path, pending)
    with pytest.raises(ScreeningError, match=r"pending|reviewer|rationale"):
        apply_screening(ledger_path, decisions_path, SCHEMA)
    # Extra decision for a non-pending transition.
    extra = copy.deepcopy(worksheet)
    ghost = copy.deepcopy(extra["decisions"][0])
    assert isinstance(ghost, dict)
    ghost["transition_id"] = "gh-" + "0" * 20
    extra["decisions"].append(ghost)
    _write_json(decisions_path, extra)
    with pytest.raises(ScreeningError, match=r"non-pending|transition_id|bound"):
        apply_screening(ledger_path, decisions_path, SCHEMA)
    # Duplicate decision.
    dup = copy.deepcopy(worksheet)
    dup["decisions"].append(copy.deepcopy(dup["decisions"][0]))
    _write_json(decisions_path, dup)
    with pytest.raises(ScreeningError, match=r"duplicate|bound"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_b3_contaminated_cannot_become_eligible(tmp_path) -> None:
    contract, _ = _load_contract()
    entry = contract["contamination_register"][0]
    assert isinstance(entry, dict)
    repo = str(entry["repository_url"]).replace("https://github.com/", "")
    url = str(entry["repository_url"])
    baseline = str(entry["baseline_commit"])
    candidate = str(entry["candidate_commit"])
    path = str(entry["path"])
    key = selection_key(url, baseline, candidate, path)
    transition = _transition()
    transition.update(
        {
            "transition_id": f"gh-{key[:20]}",
            "repository_full_name": repo,
            "repository_url": url,
            "path": path,
            "baseline_commit": baseline,
            "candidate_commit": candidate,
            "selection_key": key,
            "contamination_status": "pre_exposed_engineering_control",
        }
    )
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(transition))
    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    assert isinstance(decision, dict)
    decision["decision"] = "eligible"
    decision["rationale"] = "Would otherwise be eligible."
    decision["reviewer"] = "screening-reviewer"
    _write_json(decisions_path, worksheet)
    with pytest.raises(ScreeningError, match="contaminated"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_b3_reviewer_rationale_instructions_enforced(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    _write_json(ledger_path, _ledger(_transition()))
    worksheet = prepare_screening(ledger_path)
    decision = worksheet["decisions"][0]
    assert isinstance(decision, dict)
    decision["decision"] = "eligible"
    decision["rationale"] = ""
    decision["reviewer"] = ""
    _write_json(decisions_path, worksheet)
    with pytest.raises(ScreeningError, match=r"schema validation failed|reviewer|rationale"):
        apply_screening(ledger_path, decisions_path, SCHEMA)


def test_b3_no_generated_at_and_deterministic_bytes(tmp_path) -> None:
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.json"
    ledger, _ = _eligible_worksheet(ledger_path, decisions_path)
    assert isinstance(ledger, dict)
    first = apply_screening(ledger_path, decisions_path, SCHEMA)
    assert "generated_at" not in first
    assert first["schema_version"] == "permitdiff.dev/r3-screened-discovery-ledger/v1"
    assert all(
        t.get("screening_status") != "pending" for t in first["transitions"]  # type: ignore[union-attr]
    )
    second = apply_screening(ledger_path, decisions_path, SCHEMA)
    assert json.dumps(first, indent=2, sort_keys=True) == json.dumps(
        second, indent=2, sort_keys=True
    )


def test_b3_output_blindness_no_product_imports() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "screen_r3_public_benchmark_candidates.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("from permitdiff", "import permitdiff", "src.permitdiff"):
        assert forbidden not in text.replace("permitdiff.dev", "")
