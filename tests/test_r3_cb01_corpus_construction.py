from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.r3_cb01_corpus_construction as cb01
from jsonschema import Draft202012Validator
from scripts.r3_cb01_corpus_construction import (
    CB01BelowMinimumError,
    CB01ConstructionError,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)
CONTRACT_SCHEMA_PATH = ROOT / "docs" / "r3-cb01-corpus-construction-contract.schema.json"
RAW_SCHEMA_PATH = ROOT / "docs" / "r3-public-discovery-ledger-v2.schema.json"
SCREENED_SCHEMA_PATH = ROOT / "docs" / "r3-screened-discovery-ledger.schema.json"
SELECTION_SCHEMA_PATH = ROOT / "docs" / "r3-public-selection-v2.schema.json"
LINEAGE_SCHEMA_PATH = ROOT / "docs" / "r3-cb01-corpus-construction-lineage.schema.json"
MATERIALIZATION_SCHEMA_PATH = ROOT / "docs" / "r3-public-materialization-v2.schema.json"

STUDY_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _load_contract() -> tuple[dict[str, Any], bytes]:
    raw_bytes = CONTRACT_PATH.read_bytes()
    contract = json.loads(raw_bytes)
    assert isinstance(contract, dict)
    return contract, raw_bytes


def _contract_sha(contract_bytes: bytes) -> str:
    return hashlib.sha256(contract_bytes).hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


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


def _hex40(index: int) -> str:
    return f"{index:040x}"


def _hex64(index: int) -> str:
    return f"{index:064x}"


def _make_transition(
    contract: dict[str, Any],
    *,
    repo: str,
    baseline_index: int,
    candidate_index: int,
    path: str = ".claude/settings.json",
    status: str = "pending",
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    repository_url = cb01.canonical_repository_url(repo)
    baseline = _hex40(baseline_index)
    candidate = _hex40(candidate_index)
    key = cb01.selection_key_for(repository_url, baseline, candidate, path)
    transition_id = cb01.transition_id_for(repository_url, baseline, candidate, path)
    contamination = cb01.contamination_status_for(
        repository_url, baseline, candidate, path, contract
    )
    return {
        "transition_id": transition_id,
        "discovered_by": [{"query_id": "q1", "candidate_path": path}],
        "repository_full_name": repo,
        "repository_url": repository_url,
        "path": path,
        "baseline_commit": baseline,
        "candidate_commit": candidate,
        "baseline_blob": _hex40(100000 + baseline_index),
        "candidate_blob": _hex40(200000 + candidate_index),
        "baseline_sha256": _hex64(300000 + baseline_index),
        "candidate_sha256": _hex64(400000 + candidate_index),
        "baseline_size_bytes": 100,
        "candidate_size_bytes": 120,
        "candidate_commit_timestamp": "2026-09-01T00:00:00Z",
        "candidate_parent_count": 1,
        "permissions_changed": True,
        "screening_status": status,
        "exclusion_reasons": [] if reasons is None else list(reasons),
        "contamination_status": contamination,
        "selection_key": key,
        "manual_review_required": status == "pending",
    }


def _make_raw(
    contract: dict[str, Any],
    contract_bytes: bytes,
    transitions: list[dict[str, Any]],
    *,
    study_commit: str = STUDY_COMMIT,
) -> tuple[dict[str, Any], bytes]:
    raw = {
        "schema_version": "permitdiff.dev/r3-public-discovery-ledger/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": _contract_sha(contract_bytes),
        "study_repository_commit": study_commit,
        "producer_id": "permitdiff-r3-canonical-public-discovery-v2",
        "source": "github-rest-code-search-and-commit-history",
        "generated_at": "2026-09-01T00:00:00Z",
        "discovery_complete": True,
        "limitations": ["synthetic fixture"],
        "queries": _queries_from_contract(contract),
        "discovered_location_count": 1,
        "transition_count": len(transitions),
        "transitions": copy.deepcopy(transitions),
    }
    return raw, _canonical_bytes(raw)


def _make_decisions(
    raw: dict[str, Any],
    raw_bytes: bytes,
    *,
    eligible_all: bool = True,
) -> tuple[dict[str, Any], bytes]:
    decisions_list: list[dict[str, Any]] = []
    for item in raw["transitions"]:
        assert isinstance(item, dict)
        if item["screening_status"] != "pending":
            continue
        decision_value = "eligible" if eligible_all else "excluded"
        reasons: list[str] = [] if eligible_all else ["insufficient_public_semantics"]
        decisions_list.append(
            {
                "transition_id": item["transition_id"],
                "repository_url": item["repository_url"],
                "path": item["path"],
                "baseline_commit": item["baseline_commit"],
                "candidate_commit": item["candidate_commit"],
                "permissions_changed": item["permissions_changed"],
                "contamination_status": item["contamination_status"],
                "decision": decision_value,
                "exclusion_reasons": reasons,
                "rationale": "synthetic output-blind review with sufficient semantics",
                "reviewer": "synthetic-reviewer",
            }
        )
    payload = {
        "schema_version": "permitdiff.dev/r3-screening-decisions/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_ledger_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "generated_at": "2026-09-02T00:00:00Z",
        "instructions": "synthetic instructions",
        "decisions": decisions_list,
    }
    return payload, _canonical_bytes(payload)


def _eligible_pool(
    contract: dict[str, Any], count: int, *, repos: list[str] | None = None
) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = []
    for index in range(count):
        repo = repos[index % len(repos)] if repos else f"org/repo-{index:03d}"
        path = ".claude/settings.json" if index % 2 == 0 else ".claude/settings.local.json"
        transitions.append(
            _make_transition(
                contract,
                repo=repo,
                baseline_index=1000 + index * 2,
                candidate_index=1000 + index * 2 + 1,
                path=path,
                status="pending",
            )
        )
    return transitions


def _screened_with_eligible(
    contract: dict[str, Any],
    contract_bytes: bytes,
    count: int,
    *,
    repos: list[str] | None = None,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, dict[str, Any], bytes]:
    raw, raw_bytes = _make_raw(
        contract, contract_bytes, _eligible_pool(contract, count, repos=repos)
    )
    decisions, decisions_bytes = _make_decisions(raw, raw_bytes, eligible_all=True)
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    screened_bytes = _canonical_bytes(screened)
    return raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes


# ---------------------------------------------------------------------------
# Query-frame oracle tests (contract is the independent oracle)
# ---------------------------------------------------------------------------


def test_valid_exact_10_query_frame() -> None:
    contract, contract_bytes = _load_contract()
    frame = contract["search_frame"]
    assert len(frame) == 10
    pairs = [(entry["query_id"], entry["candidate_path"]) for entry in frame]
    assert len(set(pairs)) == 10
    assert {entry["query_id"] for entry in frame} == {"q1", "q2", "q3", "q4", "q5"}
    # Cartesian product structure: every q1-q5 concept appears with both paths.
    for query_id in ("q1", "q2", "q3", "q4", "q5"):
        paths = sorted(entry["candidate_path"] for entry in frame if entry["query_id"] == query_id)
        assert paths == [".claude/settings.json", ".claude/settings.local.json"]
    raw, raw_bytes = _make_raw(contract, contract_bytes, [])
    cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_query_frame_matches_frozen_cartesian_strings() -> None:
    contract, _ = _load_contract()
    expected = {
        (
            "q1",
            ".claude/settings.json",
        ): '"defaultMode" "dontAsk" "permissions" "allow" path:.claude filename:settings.json',
        (
            "q2",
            ".claude/settings.json",
        ): '"permissions" "allow" "ask" "deny" "settings" path:.claude filename:settings.json',
        (
            "q3",
            ".claude/settings.json",
        ): '"WebFetch" "domain" "permissions" "allow" path:.claude filename:settings.json',
        (
            "q4",
            ".claude/settings.json",
        ): '"Bash" "permissions" "allow" path:.claude filename:settings.json',
        (
            "q5",
            ".claude/settings.json",
        ): '"WebSearch" "permissions" "allow" path:.claude filename:settings.json',
    }
    by_pair = {(e["query_id"], e["candidate_path"]): e for e in contract["search_frame"]}
    for (query_id, path), api in expected.items():
        assert by_pair[(query_id, path)]["api_query"] == api
        local = by_pair[(query_id, path.replace("settings.json", "settings.local.json"))]
        assert local["api_query"] == api.replace(
            "filename:settings.json", "filename:settings.local.json"
        )


def test_selection_key_and_transition_id_formulas_independent() -> None:
    url = "https://github.com/org/example"
    baseline = "a" * 40
    candidate = "b" * 40
    path = ".claude/settings.json"
    expected_key = hashlib.sha256(f"{url}\n{baseline}\n{candidate}\n{path}".encode()).hexdigest()
    assert cb01.selection_key_for(url, baseline, candidate, path) == expected_key
    assert cb01.transition_id_for(url, baseline, candidate, path) == "gh-" + expected_key[:20]
    assert cb01.canonical_repository_url("org/example") == url


def test_rejects_fabricated_query_concept() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["queries"][0] = dict(raw["queries"][0])
    raw["queries"][0]["concept"] = "fabricated concept"
    with pytest.raises(CB01ConstructionError, match="frozen frame"):
        cb01.validate_raw_ledger(raw, _canonical_bytes(raw), contract, contract_bytes)


def test_rejects_wrong_api_query() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["queries"][3] = dict(raw["queries"][3])
    raw["queries"][3]["api_query"] = '"tampered" path:.claude filename:settings.json'
    with pytest.raises(CB01ConstructionError, match="frozen frame"):
        cb01.validate_raw_ledger(raw, _canonical_bytes(raw), contract, contract_bytes)


def test_rejects_missing_query_path_combination() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["queries"] = raw["queries"][:9]
    raw_bytes = _canonical_bytes(raw)
    with pytest.raises(CB01ConstructionError, match="exactly ten"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_rejects_duplicate_query_path_combination() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["queries"] = list(raw["queries"])
    raw["queries"][9] = copy.deepcopy(raw["queries"][0])
    with pytest.raises(CB01ConstructionError, match=r"duplicate|frozen frame"):
        cb01.validate_raw_ledger(raw, _canonical_bytes(raw), contract, contract_bytes)


def test_rejects_extra_query_entry() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["queries"] = [*list(raw["queries"]), copy.deepcopy(raw["queries"][0])]
    with pytest.raises(CB01ConstructionError, match="exactly ten"):
        cb01.validate_raw_ledger(raw, _canonical_bytes(raw), contract, contract_bytes)


# ---------------------------------------------------------------------------
# Raw-ledger adversarial tests
# ---------------------------------------------------------------------------


def test_raw_rejects_eligible_state() -> None:
    contract, contract_bytes = _load_contract()
    transitions = [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)]
    transitions[0]["screening_status"] = "eligible"
    transitions[0]["manual_review_required"] = False
    raw, raw_bytes = _make_raw(contract, contract_bytes, transitions)
    with pytest.raises(CB01ConstructionError, match="must not use eligible"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_raw_rejects_repository_url_mismatch() -> None:
    contract, contract_bytes = _load_contract()
    transitions = [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)]
    transitions[0]["repository_url"] = "https://github.com/org/other"
    raw, raw_bytes = _make_raw(contract, contract_bytes, transitions)
    with pytest.raises(CB01ConstructionError, match="repository_url/full-name mismatch"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_raw_rejects_transition_id_tamper() -> None:
    contract, contract_bytes = _load_contract()
    transitions = [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)]
    transitions[0]["transition_id"] = "gh-" + "0" * 20
    raw, raw_bytes = _make_raw(contract, contract_bytes, transitions)
    with pytest.raises(CB01ConstructionError, match="transition_id mismatch"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_raw_rejects_selection_key_tamper() -> None:
    contract, contract_bytes = _load_contract()
    transitions = [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)]
    transitions[0]["selection_key"] = "0" * 64
    raw, raw_bytes = _make_raw(contract, contract_bytes, transitions)
    with pytest.raises(CB01ConstructionError, match="selection_key mismatch"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_raw_rejects_contamination_status_tamper() -> None:
    contract, contract_bytes = _load_contract()
    transitions = [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)]
    assert transitions[0]["contamination_status"] == "clean"
    transitions[0]["contamination_status"] = "pre_exposed_engineering_control"
    raw, raw_bytes = _make_raw(contract, contract_bytes, transitions)
    with pytest.raises(CB01ConstructionError, match="contamination_status mismatch"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_raw_rejects_contaminated_identity_claiming_clean() -> None:
    contract, contract_bytes = _load_contract()
    entry = contract["contamination_register"][0]
    repo = entry["repository_url"].replace("https://github.com/", "")
    repository_url = entry["repository_url"]
    baseline = entry["baseline_commit"]
    candidate = entry["candidate_commit"]
    path = entry["path"]
    key = cb01.selection_key_for(repository_url, baseline, candidate, path)
    transition = {
        "transition_id": "gh-" + key[:20],
        "discovered_by": [{"query_id": "q1", "candidate_path": path}],
        "repository_full_name": repo,
        "repository_url": repository_url,
        "path": path,
        "baseline_commit": baseline,
        "candidate_commit": candidate,
        "baseline_blob": "1" * 40,
        "candidate_blob": "2" * 40,
        "baseline_sha256": "3" * 64,
        "candidate_sha256": "4" * 64,
        "baseline_size_bytes": 10,
        "candidate_size_bytes": 12,
        "candidate_commit_timestamp": "2026-09-01T00:00:00Z",
        "candidate_parent_count": 1,
        "permissions_changed": True,
        "screening_status": "pending",
        "exclusion_reasons": [],
        "contamination_status": "clean",
        "selection_key": key,
        "manual_review_required": True,
    }
    raw, raw_bytes = _make_raw(contract, contract_bytes, [transition])
    with pytest.raises(CB01ConstructionError, match="contamination_status mismatch"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_raw_rejects_duplicate_immutable_identity() -> None:
    contract, contract_bytes = _load_contract()
    first = _make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)
    raw, raw_bytes = _make_raw(contract, contract_bytes, [first, copy.deepcopy(first)])
    with pytest.raises(CB01ConstructionError, match="duplicate immutable transition identity"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_duplicate_selection_key_helper_rejects() -> None:
    first = {
        "repository_url": "u1",
        "baseline_commit": "a",
        "candidate_commit": "b",
        "path": "p",
        "selection_key": "k",
        "transition_id": "t1",
    }
    second = {
        "repository_url": "u2",
        "baseline_commit": "c",
        "candidate_commit": "d",
        "path": "p",
        "selection_key": "k",
        "transition_id": "t2",
    }
    with pytest.raises(CB01ConstructionError, match="duplicate selection_key"):
        cb01._check_duplicates([first, second], context="screened")


def test_duplicate_transition_id_helper_rejects() -> None:
    first = {
        "repository_url": "u1",
        "baseline_commit": "a",
        "candidate_commit": "b",
        "path": "p",
        "selection_key": "k1",
        "transition_id": "t",
    }
    second = {
        "repository_url": "u2",
        "baseline_commit": "c",
        "candidate_commit": "d",
        "path": "p",
        "selection_key": "k2",
        "transition_id": "t",
    }
    with pytest.raises(CB01ConstructionError, match="duplicate transition_id"):
        cb01._check_duplicates([first, second], context="screened")


def test_raw_rejects_wrong_producer() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["producer_id"] = "legacy-producer"
    with pytest.raises(CB01ConstructionError, match="producer_id"):
        cb01.validate_raw_ledger(raw, _canonical_bytes(raw), contract, contract_bytes)


def test_raw_rejects_contract_digest_mismatch() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(contract, contract_bytes, [])
    raw["cb01_contract_sha256"] = "0" * 64
    with pytest.raises(CB01ConstructionError, match="cb01_contract_sha256"):
        cb01.validate_raw_ledger(raw, _canonical_bytes(raw), contract, contract_bytes)


def test_raw_rejects_object_bytes_mismatch() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes = _make_raw(contract, contract_bytes, [])
    tampered = copy.deepcopy(raw)
    tampered["discovered_location_count"] = 999
    with pytest.raises(CB01ConstructionError, match="does not match exact raw bytes"):
        cb01.validate_raw_ledger(tampered, raw_bytes, contract, contract_bytes)


# ---------------------------------------------------------------------------
# Screening-derivation adversarial tests
# ---------------------------------------------------------------------------


def test_screening_rejects_raw_byte_digest_mismatch() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    decisions, _ = _make_decisions(raw, raw_bytes)
    mutated_raw = copy.deepcopy(raw)
    mutated_raw["discovered_location_count"] = 2
    mutated_bytes = _canonical_bytes(mutated_raw)
    with pytest.raises(CB01ConstructionError, match="not bound to the supplied raw bytes"):
        cb01.derive_screened_ledger(
            mutated_raw,
            mutated_bytes,
            decisions,
            _canonical_bytes(decisions),
            contract,
            contract_bytes,
        )


def test_screening_rejects_missing_decision() -> None:
    contract, contract_bytes = _load_contract()
    transitions = [
        _make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2),
        _make_transition(contract, repo="org/b", baseline_index=3, candidate_index=4),
    ]
    raw, raw_bytes = _make_raw(contract, contract_bytes, transitions)
    decisions, _ = _make_decisions(raw, raw_bytes)
    decisions["decisions"] = decisions["decisions"][:1]
    with pytest.raises(CB01ConstructionError, match="missing pending"):
        cb01.derive_screened_ledger(
            raw, raw_bytes, decisions, _canonical_bytes(decisions), contract, contract_bytes
        )


def test_screening_rejects_extra_decision() -> None:
    contract, contract_bytes = _load_contract()
    pending = _make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)
    excluded = _make_transition(
        contract,
        repo="org/b",
        baseline_index=3,
        candidate_index=4,
        status="excluded",
        reasons=["artifact_parse_failure"],
    )
    excluded["manual_review_required"] = False
    raw, raw_bytes = _make_raw(contract, contract_bytes, [pending, excluded])
    decisions, _ = _make_decisions(raw, raw_bytes)
    assert len(decisions["decisions"]) == 1
    extra = copy.deepcopy(decisions["decisions"][0])
    extra["transition_id"] = excluded["transition_id"]
    extra["repository_url"] = excluded["repository_url"]
    extra["baseline_commit"] = excluded["baseline_commit"]
    extra["candidate_commit"] = excluded["candidate_commit"]
    extra["path"] = excluded["path"]
    extra["permissions_changed"] = excluded["permissions_changed"]
    extra["contamination_status"] = excluded["contamination_status"]
    decisions["decisions"].append(extra)
    with pytest.raises(CB01ConstructionError, match="non-pending"):
        cb01.derive_screened_ledger(
            raw, raw_bytes, decisions, _canonical_bytes(decisions), contract, contract_bytes
        )


def test_screening_rejects_duplicate_decision() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    decisions, _ = _make_decisions(raw, raw_bytes)
    decisions["decisions"].append(copy.deepcopy(decisions["decisions"][0]))
    with pytest.raises(CB01ConstructionError, match="duplicate screening decision"):
        cb01.derive_screened_ledger(
            raw, raw_bytes, decisions, _canonical_bytes(decisions), contract, contract_bytes
        )


def test_screening_rejects_decision_metadata_tamper() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    decisions, _ = _make_decisions(raw, raw_bytes)
    decisions["decisions"][0]["repository_url"] = "https://github.com/org/other"
    with pytest.raises(CB01ConstructionError, match="metadata mismatch"):
        cb01.derive_screened_ledger(
            raw, raw_bytes, decisions, _canonical_bytes(decisions), contract, contract_bytes
        )


def test_screening_rejects_contaminated_marked_eligible() -> None:
    contract, contract_bytes = _load_contract()
    entry = contract["contamination_register"][0]
    repo = entry["repository_url"].replace("https://github.com/", "")
    repository_url = entry["repository_url"]
    baseline = entry["baseline_commit"]
    candidate = entry["candidate_commit"]
    path = entry["path"]
    key = cb01.selection_key_for(repository_url, baseline, candidate, path)
    transition = {
        "transition_id": "gh-" + key[:20],
        "discovered_by": [{"query_id": "q1", "candidate_path": path}],
        "repository_full_name": repo,
        "repository_url": repository_url,
        "path": path,
        "baseline_commit": baseline,
        "candidate_commit": candidate,
        "baseline_blob": "1" * 40,
        "candidate_blob": "2" * 40,
        "baseline_sha256": "3" * 64,
        "candidate_sha256": "4" * 64,
        "baseline_size_bytes": 10,
        "candidate_size_bytes": 12,
        "candidate_commit_timestamp": "2026-09-01T00:00:00Z",
        "candidate_parent_count": 1,
        "permissions_changed": True,
        "screening_status": "pending",
        "exclusion_reasons": [],
        "contamination_status": "pre_exposed_engineering_control",
        "selection_key": key,
        "manual_review_required": True,
    }
    raw, raw_bytes = _make_raw(contract, contract_bytes, [transition])
    cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)
    decisions, _ = _make_decisions(raw, raw_bytes, eligible_all=True)
    with pytest.raises(CB01ConstructionError, match="contaminated transition cannot be eligible"):
        cb01.derive_screened_ledger(
            raw, raw_bytes, decisions, _canonical_bytes(decisions), contract, contract_bytes
        )


def test_screening_rejects_pending_decision_outcome() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    decisions, _ = _make_decisions(raw, raw_bytes)
    decisions["decisions"][0]["decision"] = "pending"
    decisions["decisions"][0]["rationale"] = None
    decisions["decisions"][0]["reviewer"] = None
    with pytest.raises(CB01ConstructionError, match="remains pending"):
        cb01.derive_screened_ledger(
            raw, raw_bytes, decisions, _canonical_bytes(decisions), contract, contract_bytes
        )


def test_fabricated_screened_output_rejected_by_lineage() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection_bytes = _canonical_bytes(selection)
    fabricated = copy.deepcopy(screened)
    fabricated["transitions"][0]["screening_status"] = "excluded"
    fabricated["transitions"][0]["exclusion_reasons"] = ["insufficient_public_semantics"]
    fabricated_bytes = _canonical_bytes(fabricated)
    with pytest.raises(CB01ConstructionError, match="differs from deterministic"):
        cb01.derive_lineage_v1(
            raw,
            raw_bytes,
            decisions,
            decisions_bytes,
            fabricated,
            fabricated_bytes,
            selection,
            selection_bytes,
            contract,
            contract_bytes,
        )


def test_exact_parent_byte_digests() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    assert screened["source_discovery_ledger_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert (
        screened["source_screening_decisions_sha256"] == hashlib.sha256(decisions_bytes).hexdigest()
    )
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection_bytes = _canonical_bytes(selection)
    assert selection["source_screened_ledger_sha256"] == hashlib.sha256(screened_bytes).hexdigest()
    lineage = cb01.derive_lineage_v1(
        raw,
        raw_bytes,
        decisions,
        decisions_bytes,
        screened,
        screened_bytes,
        selection,
        selection_bytes,
        contract,
        contract_bytes,
    )
    assert lineage["raw_discovery_ledger_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert lineage["screening_decisions_sha256"] == hashlib.sha256(decisions_bytes).hexdigest()
    assert lineage["screened_discovery_ledger_sha256"] == hashlib.sha256(screened_bytes).hexdigest()
    assert lineage["public_selection_sha256"] == hashlib.sha256(selection_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Count semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("eligible_count", "should_succeed"),
    [(0, False), (11, False), (12, True), (17, True), (18, True), (25, True)],
)
def test_count_semantics_distinct_repos(eligible_count: int, should_succeed: bool) -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, eligible_count
    )
    counts = cb01.derive_counts(screened)
    assert counts["raw_eligible_count"] == eligible_count
    assert counts["cap_admissible_count"] == eligible_count
    if should_succeed:
        selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
        assert selection["selected_case_count"] == min(eligible_count, 18)
        assert selection["shortfall"] == 18 - min(eligible_count, 18)
    else:
        with pytest.raises(CB01BelowMinimumError):
            cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)


def test_count_12_raw_11_cap_fails() -> None:
    contract, contract_bytes = _load_contract()
    repos = ["org/concentrated"] * 3 + [f"org/repo-{index:03d}" for index in range(9)]
    assert len(repos) == 12
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12, repos=repos
    )
    counts = cb01.derive_counts(screened)
    assert counts["raw_eligible_count"] == 12
    assert counts["cap_admissible_count"] == 11
    with pytest.raises(CB01BelowMinimumError):
        cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)


def test_count_12_12_succeeds_shortfall_6() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert selection["raw_eligible_count"] == 12
    assert selection["cap_admissible_count"] == 12
    assert selection["selected_case_count"] == 12
    assert selection["shortfall"] == 6


def test_count_17_17_succeeds_shortfall_1() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 17)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert selection["selected_case_count"] == 17
    assert selection["shortfall"] == 1


def test_count_18_18_succeeds_shortfall_0() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 18)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert selection["selected_case_count"] == 18
    assert selection["shortfall"] == 0


def test_count_over_18_under_12_cap_fails() -> None:
    contract, contract_bytes = _load_contract()
    repos = [f"org/repo-{index % 5:03d}" for index in range(20)]
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 20, repos=repos
    )
    counts = cb01.derive_counts(screened)
    assert counts["raw_eligible_count"] == 20
    assert counts["cap_admissible_count"] == 10
    with pytest.raises(CB01BelowMinimumError):
        cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)


def test_count_over_18_cap_17_succeeds() -> None:
    contract, contract_bytes = _load_contract()
    repos = (
        ["org/heavy"] * 4 + ["org/medium"] * 3 + [f"org/repo-{index:03d}" for index in range(13)]
    )
    assert len(repos) == 20
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 20, repos=repos
    )
    counts = cb01.derive_counts(screened)
    assert counts["raw_eligible_count"] == 20
    assert counts["cap_admissible_count"] == 17
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert selection["selected_case_count"] == 17
    assert selection["shortfall"] == 1


def test_count_over_18_selects_exactly_18() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 25)
    counts = cb01.derive_counts(screened)
    assert counts["cap_admissible_count"] == 25
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert selection["selected_case_count"] == 18
    assert selection["shortfall"] == 0
    keys = [item["selection_key"] for item in selection["selected"]]
    assert keys == sorted(keys)


def test_repository_concentration_cap_selected() -> None:
    contract, contract_bytes = _load_contract()
    # Heavy concentration: 30 eligible from 2 repos -> cap 4 -> failure.
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 30, repos=["org/a", "org/b"]
    )
    counts = cb01.derive_counts(screened)
    assert counts["raw_eligible_count"] == 30
    assert counts["cap_admissible_count"] == 4
    with pytest.raises(CB01BelowMinimumError):
        cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)


def test_raw_eligible_count_is_transparency_only() -> None:
    contract, contract_bytes = _load_contract()
    repos = ["org/a"] * 30
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 30, repos=repos
    )
    counts = cb01.derive_counts(screened)
    assert counts["raw_eligible_count"] == 30
    assert counts["cap_admissible_count"] == 2
    with pytest.raises(CB01BelowMinimumError):
        cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)


# ---------------------------------------------------------------------------
# Byte binding, determinism, and same-study-commit
# ---------------------------------------------------------------------------


def test_selection_binds_exact_screened_bytes() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert selection["source_screened_ledger_sha256"] == hashlib.sha256(screened_bytes).hexdigest()
    reformatted = json.dumps(screened, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    assert json.loads(reformatted) == screened
    assert hashlib.sha256(reformatted).hexdigest() != selection["source_screened_ledger_sha256"]


def test_formatting_changes_produce_different_parent_digests() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    compact = json.dumps(screened, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    assert json.loads(compact) == screened
    assert hashlib.sha256(compact).hexdigest() != hashlib.sha256(screened_bytes).hexdigest()


def test_deterministic_outputs_are_stable() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes = _make_raw(contract, contract_bytes, _eligible_pool(contract, 12))
    decisions, decisions_bytes = _make_decisions(raw, raw_bytes)
    first_screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    second_screened = cb01.derive_screened_ledger(
        copy.deepcopy(raw),
        raw_bytes,
        copy.deepcopy(decisions),
        decisions_bytes,
        contract,
        contract_bytes,
    )
    assert first_screened == second_screened
    first_bytes = _canonical_bytes(first_screened)
    second_bytes = _canonical_bytes(second_screened)
    assert first_bytes == second_bytes
    first_selection = cb01.derive_selection_v2(
        first_screened, first_bytes, contract, contract_bytes
    )
    second_selection = cb01.derive_selection_v2(
        second_screened, second_bytes, contract, contract_bytes
    )
    assert first_selection == second_selection


def test_derived_artifacts_contain_no_generated_at() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    assert "generated_at" not in screened
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    assert "generated_at" not in selection
    lineage = cb01.derive_lineage_v1(
        raw,
        raw_bytes,
        decisions,
        decisions_bytes,
        screened,
        screened_bytes,
        selection,
        _canonical_bytes(selection),
        contract,
        contract_bytes,
    )
    assert "generated_at" not in lineage


def test_same_study_commit_enforced() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    assert screened["study_repository_commit"] == STUDY_COMMIT
    tampered = copy.deepcopy(screened)
    tampered["study_repository_commit"] = "f" * 40
    tampered_bytes = _canonical_bytes(tampered)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection_bytes = _canonical_bytes(selection)
    with pytest.raises(
        CB01ConstructionError, match=r"differs from deterministic|study_repository_commit"
    ):
        cb01.derive_lineage_v1(
            raw,
            raw_bytes,
            decisions,
            decisions_bytes,
            tampered,
            tampered_bytes,
            selection,
            selection_bytes,
            contract,
            contract_bytes,
        )


def test_lineage_rejects_study_commit_mismatch_in_selection() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection["study_repository_commit"] = "e" * 40
    selection_bytes = _canonical_bytes(selection)
    with pytest.raises(
        CB01ConstructionError, match=r"study_repository_commit|differs from deterministic"
    ):
        cb01.derive_lineage_v1(
            raw,
            raw_bytes,
            decisions,
            decisions_bytes,
            screened,
            screened_bytes,
            selection,
            selection_bytes,
            contract,
            contract_bytes,
        )


def test_no_network_imports_in_pure_module() -> None:
    text = (ROOT / "scripts" / "r3_cb01_corpus_construction.py").read_text(encoding="utf-8")
    import_lines = [
        line for line in text.splitlines() if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    for forbidden in ("urllib", "http.client", "socket", "requests", "urlopen"):
        assert forbidden not in joined


def test_below_minimum_returns_no_payload() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 5)
    with pytest.raises(CB01BelowMinimumError):
        cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)


def test_selection_rejects_legacy_eligible_case_count() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection["eligible_case_count"] = 12
    with pytest.raises(CB01ConstructionError, match="legacy eligible_case_count"):
        cb01.validate_selection_v2(selection, contract, contract_bytes)


# ---------------------------------------------------------------------------
# Schema tests (Draft 2020-12)
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_all_new_schemas_are_valid_draft_2020_12() -> None:
    for path in (
        CONTRACT_SCHEMA_PATH,
        RAW_SCHEMA_PATH,
        SCREENED_SCHEMA_PATH,
        SELECTION_SCHEMA_PATH,
        LINEAGE_SCHEMA_PATH,
        MATERIALIZATION_SCHEMA_PATH,
    ):
        Draft202012Validator.check_schema(_load_json(path))


def test_contract_validates_against_its_schema() -> None:
    schema = _load_json(CONTRACT_SCHEMA_PATH)
    contract, _ = _load_contract()
    Draft202012Validator(schema).validate(contract)


def test_valid_raw_conforms_to_schema() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    Draft202012Validator(_load_json(RAW_SCHEMA_PATH)).validate(raw)


def test_raw_schema_rejects_eligible() -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    raw["transitions"][0]["screening_status"] = "eligible"
    errors = list(Draft202012Validator(_load_json(RAW_SCHEMA_PATH)).iter_errors(raw))
    assert errors


def test_valid_screened_conforms_to_schema() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, _ = _screened_with_eligible(contract, contract_bytes, 2)
    Draft202012Validator(_load_json(SCREENED_SCHEMA_PATH)).validate(screened)


def test_screened_schema_rejects_pending() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, _ = _screened_with_eligible(contract, contract_bytes, 2)
    screened["transitions"][0]["screening_status"] = "pending"
    errors = list(Draft202012Validator(_load_json(SCREENED_SCHEMA_PATH)).iter_errors(screened))
    assert errors


def test_valid_selection_conforms_to_schema() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    Draft202012Validator(_load_json(SELECTION_SCHEMA_PATH)).validate(selection)


def test_selection_schema_rejects_legacy_field() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection["eligible_case_count"] = selection["raw_eligible_count"]
    errors = list(Draft202012Validator(_load_json(SELECTION_SCHEMA_PATH)).iter_errors(selection))
    assert errors


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("target_case_count", 17),
        ("maximum_cases_per_repository", 3),
        ("minimum_viable_case_count", 11),
    ],
)
def test_selection_schema_rejects_non_frozen_constants(field: str, bad: int) -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection[field] = bad
    errors = list(Draft202012Validator(_load_json(SELECTION_SCHEMA_PATH)).iter_errors(selection))
    assert errors


def test_valid_lineage_conforms_to_schema() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    lineage = cb01.derive_lineage_v1(
        raw,
        raw_bytes,
        decisions,
        decisions_bytes,
        screened,
        screened_bytes,
        selection,
        _canonical_bytes(selection),
        contract,
        contract_bytes,
    )
    Draft202012Validator(_load_json(LINEAGE_SCHEMA_PATH)).validate(lineage)


def test_lineage_schema_rejects_non_frozen_target() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes, screened, screened_bytes = _screened_with_eligible(
        contract, contract_bytes, 12
    )
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    lineage = cb01.derive_lineage_v1(
        raw,
        raw_bytes,
        decisions,
        decisions_bytes,
        screened,
        screened_bytes,
        selection,
        _canonical_bytes(selection),
        contract,
        contract_bytes,
    )
    lineage["target_case_count"] = 17
    errors = list(Draft202012Validator(_load_json(LINEAGE_SCHEMA_PATH)).iter_errors(lineage))
    assert errors


def test_valid_materialization_v2_conforms_to_schema() -> None:
    contract, contract_bytes = _load_contract()
    _, _, _, _, screened, screened_bytes = _screened_with_eligible(contract, contract_bytes, 12)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    materialization = {
        "schema_version": "permitdiff.dev/r3-public-materialization/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_selection_sha256": hashlib.sha256(_canonical_bytes(selection)).hexdigest(),
        "source_cb01_lineage_sha256": "a" * 64,
        "study_repository_commit": STUDY_COMMIT,
        "generated_at": "2026-09-03T00:00:00Z",
        "selected_case_count": 1,
        "cases": [
            {
                "rank": 1,
                "transition_id": selection["selected"][0]["transition_id"],
                "repository_full_name": selection["selected"][0]["repository_full_name"],
                "repository_url": selection["selected"][0]["repository_url"],
                "source_path": selection["selected"][0]["path"],
                "selection_key": selection["selected"][0]["selection_key"],
                "baseline": {
                    "path": f"cases/{selection['selected'][0]['transition_id']}/baseline.json",
                    "sha256": selection["selected"][0]["baseline_sha256"],
                    "source_url": "https://github.com/org/repo-000/blob/aaa/file",
                    "source_commit": selection["selected"][0]["baseline_commit"],
                    "source_blob": selection["selected"][0]["baseline_blob"],
                    "size_bytes": 10,
                },
                "candidate": {
                    "path": f"cases/{selection['selected'][0]['transition_id']}/candidate.json",
                    "sha256": selection["selected"][0]["candidate_sha256"],
                    "source_url": "https://github.com/org/repo-000/blob/bbb/file",
                    "source_commit": selection["selected"][0]["candidate_commit"],
                    "source_blob": selection["selected"][0]["candidate_blob"],
                    "size_bytes": 12,
                },
            }
        ],
    }
    Draft202012Validator(_load_json(MATERIALIZATION_SCHEMA_PATH)).validate(materialization)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw["transitions"].__setitem__(
            0, {**raw["transitions"][0], "selection_key": "zzz"}
        ),
        lambda raw: raw.update({"unexpected_property": True}),
        lambda raw: raw.update({"cb01_contract_sha256": "not-a-sha"}),
    ],
)
def test_raw_schema_rejects_malformed(mutate: Any) -> None:
    contract, contract_bytes = _load_contract()
    raw, _ = _make_raw(
        contract,
        contract_bytes,
        [_make_transition(contract, repo="org/a", baseline_index=1, candidate_index=2)],
    )
    mutate(raw)
    errors = list(Draft202012Validator(_load_json(RAW_SCHEMA_PATH)).iter_errors(raw))
    assert errors
