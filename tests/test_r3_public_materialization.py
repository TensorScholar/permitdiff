"""Packet B5 lineage-gated materialization tests (synthetic only).

All fixtures are synthetic. No GitHub access, no tokens, no discovery,
no real R3 evidence. Writes go only to ``tmp_path`` fixtures. Every
pre-fetch failure asserts no source fetch occurred (``file_calls == []``)
and no partial output directory exists.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.r3_cb01_corpus_construction as cb01
from scripts.materialize_r3_public_selection import (
    MaterializationError,
    materialize_selection,
)

ROOT = Path(__file__).resolve().parents[1]
SELECTION_SCHEMA = ROOT / "docs" / "r3-public-selection-v2.schema.json"
LINEAGE_SCHEMA = ROOT / "docs" / "r3-cb01-corpus-construction-lineage.schema.json"
MATERIALIZATION_SCHEMA = ROOT / "docs" / "r3-public-materialization-v2.schema.json"
CONTRACT_PATH = (
    ROOT
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)

_STUDY = "2" * 40


class FakeClient:
    """Generic mocked source client: serves fixed bytes per (repo, path, commit)."""

    def __init__(
        self,
        files: dict[tuple[str, str, str], tuple[str, bytes]],
        *,
        private_repos: set[str] | None = None,
        renamed: dict[str, str] | None = None,
    ) -> None:
        self.files = files
        self.private_repos = private_repos or set()
        self.renamed = renamed or {}
        self.repository_calls = 0
        self.file_calls: list[tuple[str, str, str]] = []

    def get_json(self, endpoint: str, params: Any = None) -> dict[str, Any]:
        assert endpoint.startswith("/repos/")
        repo = endpoint[len("/repos/") :]
        self.repository_calls += 1
        if repo in self.private_repos:
            return {"full_name": repo, "private": True}
        return {"full_name": self.renamed.get(repo, repo), "private": False}

    def get_file(self, repository: str, path: str, ref: str) -> tuple[dict[str, Any], bytes]:
        self.file_calls.append((repository, path, ref))
        blob, raw = self.files[(repository, path, ref)]
        return {"sha": blob}, raw


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


def _build_chain(
    count: int = 12, *, repos: list[str] | None = None
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, dict[str, Any]]:
    """Build selection v2 + lineage v1 with served file bytes (synthetic)."""
    contract, contract_bytes = _load_contract()
    transitions: list[dict[str, Any]] = []
    served: dict[tuple[str, str, str], tuple[str, bytes]] = {}
    for index in range(count):
        repo = repos[index % len(repos)] if repos else f"org/b5-case-{index:03d}"
        path = ".claude/settings.json" if index % 2 == 0 else ".claude/settings.local.json"
        url = f"https://github.com/{repo}"
        baseline = f"{index + 4000:040x}"
        candidate = f"{index + 8000:040x}"
        baseline_raw = (
            json.dumps({"permissions": {"allow": []}, "case": index}, sort_keys=True).encode()
            + b"\n"
        )
        candidate_raw = (
            json.dumps({"permissions": {"allow": ["Bash"]}, "case": index}, sort_keys=True).encode()
            + b"\n"
        )
        baseline_blob = f"{index + 500:040x}"
        candidate_blob = f"{index + 600:040x}"
        served[(repo, path, baseline)] = (baseline_blob, baseline_raw)
        served[(repo, path, candidate)] = (candidate_blob, candidate_raw)
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
                "baseline_blob": baseline_blob,
                "candidate_blob": candidate_blob,
                "baseline_sha256": hashlib.sha256(baseline_raw).hexdigest(),
                "candidate_sha256": hashlib.sha256(candidate_raw).hexdigest(),
                "baseline_size_bytes": len(baseline_raw),
                "candidate_size_bytes": len(candidate_raw),
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
        "limitations": ["b5 synthetic fixture"],
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
        "instructions": "b5 synthetic instructions",
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
                "rationale": "b5 synthetic eligibility",
                "reviewer": "b5-reviewer",
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
    return selection, selection_bytes, lineage, _canonical_bytes(lineage), served


def _write_pair(
    tmp_path: Path, selection: dict[str, Any], lineage: dict[str, Any]
) -> tuple[Path, Path]:
    selection_path = tmp_path / "selection.json"
    lineage_path = tmp_path / "lineage.json"
    selection_path.write_bytes(_canonical_bytes(selection))
    lineage_path.write_bytes(_canonical_bytes(lineage))
    return selection_path, lineage_path


def test_b5_valid_v2_selection_and_lineage_succeeds(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    index = materialize_selection(
        selection_path,
        lineage_path,
        output_dir,
        SELECTION_SCHEMA,
        LINEAGE_SCHEMA,
        MATERIALIZATION_SCHEMA,
        CONTRACT_PATH,
        client,
    )

    assert index["schema_version"] == "permitdiff.dev/r3-public-materialization/v2"
    assert index["study_repository_commit"] == _STUDY
    assert index["selected_case_count"] == 12
    assert len(index["cases"]) == 12
    assert (
        index["source_selection_sha256"] == hashlib.sha256(selection_path.read_bytes()).hexdigest()
    )
    assert (
        index["source_cb01_lineage_sha256"] == hashlib.sha256(lineage_path.read_bytes()).hexdigest()
    )
    assert json.loads((output_dir / "materialization.json").read_text()) == index
    first = index["cases"][0]
    tid = first["transition_id"]
    assert (output_dir / f"cases/{tid}/baseline.json").exists()
    assert (output_dir / f"cases/{tid}/candidate.json").exists()
    assert len(client.file_calls) == 24


def test_b5_selection_v1_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    v1 = copy.deepcopy(selection)
    v1["schema_version"] = "permitdiff.dev/r3-public-selection/v1"
    v1["target_cases"] = 18
    v1["eligible_case_count"] = v1["raw_eligible_count"]
    v1["source_ledger_sha256"] = "9" * 64
    selection_path, lineage_path = _write_pair(tmp_path, v1, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"schema|unsupported|legacy"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_missing_lineage_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, _, _, served = _build_chain()
    selection_path = tmp_path / "selection.json"
    selection_path.write_bytes(_canonical_bytes(selection))
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"failed to read|lineage"):
        materialize_selection(
            selection_path,
            tmp_path / "missing-lineage.json",
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_tampered_lineage_digest_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    lineage["public_selection_sha256"] = "0" * 64
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"bound|digest|schema"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_contract_mismatch_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection["cb01_contract_sha256"] = "1" * 64
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"contract|digest|schema"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_study_commit_mismatch_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    lineage["study_repository_commit"] = "3" * 40
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"study|schema"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_count_mismatch_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    lineage["selected_case_count"] = selection["selected_case_count"] + 1
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"match|count|schema"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_below_minimum_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    truncated = copy.deepcopy(selection)
    truncated["selected"] = truncated["selected"][:5]
    truncated["selected_case_count"] = 5
    truncated["shortfall"] = 13
    selection_path, lineage_path = _write_pair(tmp_path, truncated, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"minimum|below|match|count"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()


def test_b5_blob_mismatch_rejected_without_partial_output(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    first_key = next(iter(served))
    wrong = dict(served)
    wrong[first_key] = ("e" * 40, served[first_key][1])
    client = FakeClient(wrong)

    with pytest.raises(MaterializationError, match="blob mismatch"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert not output_dir.exists()


def test_b5_sha_mismatch_rejected_without_partial_output(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    first_key = next(iter(served))
    blob, raw = served[first_key]
    wrong = dict(served)
    wrong[first_key] = (blob, raw + b" ")
    client = FakeClient(wrong)

    with pytest.raises(MaterializationError, match="SHA-256 mismatch"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert not output_dir.exists()


def test_b5_private_repository_rejected_without_partial_output(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    first_repo = selection["selected"][0]["repository_full_name"]
    client = FakeClient(served, private_repos={first_repo})

    with pytest.raises(MaterializationError, match="not explicitly public"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert not output_dir.exists()


def test_b5_changed_identity_rejected_without_partial_output(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    first_repo = selection["selected"][0]["repository_full_name"]
    client = FakeClient(served, renamed={first_repo: "public/renamed"})

    with pytest.raises(MaterializationError, match="identity changed"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert not output_dir.exists()


def test_b5_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    output_dir.mkdir()
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match="refuse to overwrite evidence"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []


def test_b5_noncontiguous_ranks_rejected_before_fetch(tmp_path: Path) -> None:
    selection, _, lineage, _, served = _build_chain()
    selection["selected"][0]["rank"] = 2
    selection_path, lineage_path = _write_pair(tmp_path, selection, lineage)
    output_dir = tmp_path / "materialized"
    client = FakeClient(served)

    with pytest.raises(MaterializationError, match=r"ranks|digest|schema|match"):
        materialize_selection(
            selection_path,
            lineage_path,
            output_dir,
            SELECTION_SCHEMA,
            LINEAGE_SCHEMA,
            MATERIALIZATION_SCHEMA,
            CONTRACT_PATH,
            client,
        )

    assert client.file_calls == []
    assert not output_dir.exists()
