"""Packet C hardening tests for the v3 pre-execution lock binding (synthetic only).

All fixtures are synthetic. No GitHub access, no tokens, no discovery, no
real R3 evidence. Writes go only to ``tmp_path`` fixtures. The full
``create_v3_lock`` entrypoint additionally requires a clean git repository
plus frozen review/adjudication/manifest inputs, so these tests target the
Packet C binding logic directly:

- ``_validate_selection``: v2 derive-equality plus frozen 18/2/12,
  contiguous ranks, key ordering, repository cap, transition identity.
- ``_validate_lineage_binding``: exact-byte selection/lineage digests and
  three-way study-commit equality.
- ``_read_json``: missing/malformed lineage files fail closed.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.r3_cb01_corpus_construction as cb01
from scripts.lock_r3_exploratory_corpus_v3 import (
    V3LockError,
    _read_json,
    _validate_lineage_binding,
    _validate_selection,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)

_STUDY = "4" * 40


def _load_contract() -> tuple[dict[str, Any], bytes]:
    raw_bytes = CONTRACT_PATH.read_bytes()
    contract = json.loads(raw_bytes)
    assert isinstance(contract, dict)
    return contract, raw_bytes


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


def _valid_chain(count: int = 12, *, repos: list[str] | None = None) -> dict[str, Any]:
    """Build raw/decisions/screened/selection/lineage/materialization (synthetic)."""
    contract, contract_bytes = _load_contract()
    transitions: list[dict[str, Any]] = []
    for index in range(count):
        repo = repos[index % len(repos)] if repos else f"org/c3-lock-{index:03d}"
        path = ".claude/settings.json" if index % 2 == 0 else ".claude/settings.local.json"
        url = f"https://github.com/{repo}"
        baseline = f"{index + 1100:040x}"
        candidate = f"{index + 2200:040x}"
        key = hashlib.sha256(f"{url}\n{baseline}\n{candidate}\n{path}".encode()).hexdigest()
        transitions.append(
            {
                "transition_id": "gh-" + key[:20],
                "discovered_by": [{"query_id": "q1", "candidate_path": path}],
                "repository_full_name": repo,
                "repository_url": url,
                "path": path,
                "baseline_commit": baseline,
                "candidate_commit": candidate,
                "baseline_blob": f"{index + 330:040x}",
                "candidate_blob": f"{index + 440:040x}",
                "baseline_sha256": f"{index + 550:064x}",
                "candidate_sha256": f"{index + 660:064x}",
                "baseline_size_bytes": 100,
                "candidate_size_bytes": 120,
                "candidate_commit_timestamp": "2026-09-01T00:00:00Z",
                "candidate_parent_count": 1,
                "permissions_changed": True,
                "screening_status": "pending",
                "exclusion_reasons": [],
                "contamination_status": "clean",
                "selection_key": key,
                "manual_review_required": True,
            }
        )
    raw = {
        "schema_version": "permitdiff.dev/r3-public-discovery-ledger/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "study_repository_commit": _STUDY,
        "producer_id": "permitdiff-r3-canonical-public-discovery-v2",
        "source": "github-rest-code-search-and-commit-history",
        "generated_at": "2026-09-01T00:00:00Z",
        "discovery_complete": True,
        "limitations": ["c3 synthetic fixture"],
        "queries": _queries_from_contract(contract),
        "discovered_location_count": 1,
        "transition_count": len(transitions),
        "transitions": copy.deepcopy(transitions),
    }
    raw_bytes = _canonical_bytes(raw)
    decisions = {
        "schema_version": "permitdiff.dev/r3-screening-decisions/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_ledger_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "generated_at": "2026-09-02T00:00:00Z",
        "instructions": "c3 synthetic instructions",
        "decisions": [
            {
                "transition_id": item["transition_id"],
                "repository_url": item["repository_url"],
                "path": item["path"],
                "baseline_commit": item["baseline_commit"],
                "candidate_commit": item["candidate_commit"],
                "permissions_changed": item["permissions_changed"],
                "contamination_status": item["contamination_status"],
                "decision": "eligible",
                "exclusion_reasons": [],
                "rationale": "c3 synthetic eligibility",
                "reviewer": "c3-reviewer",
            }
            for item in transitions
        ],
    }
    decisions_bytes = _canonical_bytes(decisions)
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    screened_bytes = _canonical_bytes(screened)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection_bytes = _canonical_bytes(selection)
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
    lineage_bytes = _canonical_bytes(lineage)
    materialization = {
        "schema_version": "permitdiff.dev/r3-public-materialization/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_selection_sha256": hashlib.sha256(selection_bytes).hexdigest(),
        "source_cb01_lineage_sha256": hashlib.sha256(lineage_bytes).hexdigest(),
        "study_repository_commit": _STUDY,
        "generated_at": "2026-09-01T00:00:00Z",
        "selected_case_count": selection["selected_case_count"],
        "cases": [],
    }
    return {
        "contract": contract,
        "contract_bytes": contract_bytes,
        "screened": screened,
        "screened_bytes": screened_bytes,
        "selection": selection,
        "selection_bytes": selection_bytes,
        "lineage": lineage,
        "lineage_bytes": lineage_bytes,
        "materialization": materialization,
    }


def test_valid_v2_chain_passes_selection_and_binding() -> None:
    chain = _valid_chain()
    _validate_selection(
        chain["screened"],
        chain["screened_bytes"],
        chain["selection"],
        chain["selection_bytes"],
        chain["contract"],
        chain["contract_bytes"],
    )
    _validate_lineage_binding(
        selection=chain["selection"],
        selection_bytes=chain["selection_bytes"],
        lineage=chain["lineage"],
        lineage_bytes=chain["lineage_bytes"],
        materialization=chain["materialization"],
    )
    assert chain["selection"]["target_case_count"] == 18
    assert chain["selection"]["maximum_cases_per_repository"] == 2
    assert chain["selection"]["minimum_viable_case_count"] == 12


def _assert_selection_rejected(chain: dict[str, Any], tampered: dict[str, Any]) -> None:
    """Supplied selections differing from deterministic derivation must fail."""
    with pytest.raises(
        V3LockError, match=r"derivation failed|exact frozen deterministic selection"
    ):
        _validate_selection(
            chain["screened"],
            chain["screened_bytes"],
            tampered,
            _canonical_bytes(tampered),
            chain["contract"],
            chain["contract_bytes"],
        )


def test_frozen_target_enforced() -> None:
    chain = _valid_chain()
    tampered = copy.deepcopy(chain["selection"])
    tampered["target_case_count"] = 17
    _assert_selection_rejected(chain, tampered)


def test_frozen_cap_enforced() -> None:
    chain = _valid_chain()
    tampered = copy.deepcopy(chain["selection"])
    tampered["maximum_cases_per_repository"] = 3
    _assert_selection_rejected(chain, tampered)


def test_minimum_viable_count_enforced() -> None:
    # Below-minimum cohorts cannot produce a canonical selection at all.
    with pytest.raises(cb01.CB01ConstructionError, match=r"below frozen|minimum"):
        _valid_chain(count=5)
    # A truncated selection differs from deterministic derivation.
    chain = _valid_chain()
    truncated = copy.deepcopy(chain["selection"])
    truncated["selected"] = truncated["selected"][:5]
    truncated["selected_case_count"] = 5
    truncated["shortfall"] = 13
    _assert_selection_rejected(chain, truncated)


def test_contiguous_ranks_enforced() -> None:
    chain = _valid_chain()
    tampered = copy.deepcopy(chain["selection"])
    tampered["selected"][0]["rank"] = 99
    _assert_selection_rejected(chain, tampered)


def test_selection_key_ordering_enforced() -> None:
    chain = _valid_chain()
    tampered = copy.deepcopy(chain["selection"])
    tampered["selected"][0], tampered["selected"][1] = (
        tampered["selected"][1],
        tampered["selected"][0],
    )
    _assert_selection_rejected(chain, tampered)


def test_repository_cap_enforced() -> None:
    # A 30-case single-repository cohort cannot reach viability (cap 2).
    with pytest.raises(cb01.CB01ConstructionError, match=r"below frozen|minimum"):
        _valid_chain(count=30, repos=["org/c3-concentrated"])
    # A third same-repository case smuggled into a valid selection fails.
    chain = _valid_chain()
    tampered = copy.deepcopy(chain["selection"])
    for _ in range(2):
        tampered["selected"].append(copy.deepcopy(tampered["selected"][0]))
        tampered["selected"][-1]["rank"] = len(tampered["selected"])
    tampered["selected_case_count"] = len(tampered["selected"])
    tampered["shortfall"] = 18 - len(tampered["selected"])
    _assert_selection_rejected(chain, tampered)


def test_transition_identity_enforced() -> None:
    chain = _valid_chain()
    tampered = copy.deepcopy(chain["selection"])
    tampered["selected"][0]["baseline_commit"] = "f" * 40
    _assert_selection_rejected(chain, tampered)


def test_lineage_sha_mismatch_rejected(tmp_path: Path) -> None:
    chain = _valid_chain()
    before = {p.name for p in tmp_path.iterdir()}
    # Swapped lineage bytes no longer match the materialization digest.
    with pytest.raises(V3LockError, match=r"not bound to the exact lineage bytes"):
        _validate_lineage_binding(
            selection=chain["selection"],
            selection_bytes=chain["selection_bytes"],
            lineage=chain["lineage"],
            lineage_bytes=chain["lineage_bytes"],
            materialization={
                **chain["materialization"],
                "source_cb01_lineage_sha256": "0" * 64,
            },
        )
    assert {p.name for p in tmp_path.iterdir()} == before


def test_study_commit_mismatch_rejected(tmp_path: Path) -> None:
    chain = _valid_chain()
    before = {p.name for p in tmp_path.iterdir()}
    for holder in ("lineage", "materialization"):
        tampered_chain = copy.deepcopy(chain)
        tampered_chain[holder]["study_repository_commit"] = "5" * 40
        with pytest.raises(V3LockError, match=r"study commit does not match"):
            _validate_lineage_binding(
                selection=tampered_chain["selection"],
                selection_bytes=tampered_chain["selection_bytes"],
                lineage=tampered_chain["lineage"],
                lineage_bytes=tampered_chain["lineage_bytes"],
                materialization=tampered_chain["materialization"],
            )
    assert {p.name for p in tmp_path.iterdir()} == before


def test_selection_digest_mismatch_rejected(tmp_path: Path) -> None:
    chain = _valid_chain()
    before = {p.name for p in tmp_path.iterdir()}
    tampered_materialization = {
        **chain["materialization"],
        "source_selection_sha256": "0" * 64,
    }
    with pytest.raises(V3LockError, match=r"not bound to the exact selection bytes"):
        _validate_lineage_binding(
            selection=chain["selection"],
            selection_bytes=chain["selection_bytes"],
            lineage=chain["lineage"],
            lineage_bytes=chain["lineage_bytes"],
            materialization=tampered_materialization,
        )
    assert {p.name for p in tmp_path.iterdir()} == before


def test_missing_lineage_file_rejected(tmp_path: Path) -> None:
    before = {p.name for p in tmp_path.iterdir()}
    with pytest.raises(V3LockError, match=r"cannot read CB-01 lineage"):
        _read_json(tmp_path / "missing-lineage.json", "CB-01 lineage")
    assert {p.name for p in tmp_path.iterdir()} == before


def test_malformed_lineage_file_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "lineage.json"
    bad.write_text('{"truncated": true', encoding="utf-8")
    before = {p.name for p in tmp_path.iterdir()}
    with pytest.raises(V3LockError, match=r"not valid JSON"):
        _read_json(bad, "CB-01 lineage")
    assert {p.name for p in tmp_path.iterdir()} == before
