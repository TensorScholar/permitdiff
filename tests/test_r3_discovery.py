from __future__ import annotations

import base64
import copy
import hashlib
import json
import ssl
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
import scripts.discover_r3_benchmark_candidates as discovery
import scripts.r3_cb01_corpus_construction as cb01
from jsonschema import Draft202012Validator
from scripts.discover_r3_benchmark_candidates import (
    PLAN_VERSION,
    DiscoveryError,
    GitHubClient,
    build_ledger,
    build_search_specs,
    discover_locations,
    enumerate_transitions,
    select_public_historical,
    selection_key,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_V2_SCHEMA = ROOT / "docs" / "r3-public-discovery-ledger-v2.schema.json"
SELECTION_V2_SCHEMA = ROOT / "docs" / "r3-public-selection-v2.schema.json"
CB01_CONTRACT_PATH = (
    ROOT
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)
_SYNTHETIC_STUDY_COMMIT = "0" * 40


def _load_cb01_contract() -> tuple[dict[str, Any], bytes]:
    raw_bytes = CB01_CONTRACT_PATH.read_bytes()
    contract = json.loads(raw_bytes)
    assert isinstance(contract, dict)
    return contract, raw_bytes


class FakeClient:
    def __init__(self) -> None:
        self.search_payloads: dict[str, tuple[list[dict[str, Any]], int, bool]] = {}
        self.histories: dict[tuple[str, str], tuple[list[dict[str, Any]], bool]] = {}
        self.commits: dict[tuple[str, str], dict[str, Any]] = {}
        self.files: dict[tuple[str, str, str], tuple[dict[str, Any], bytes]] = {}

    def search_code(self, query: str) -> tuple[list[dict[str, Any]], int, bool]:
        return self.search_payloads.get(query, ([], 0, False))

    def list_path_commits(
        self, repository: str, path: str, *, max_commits: int | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        commits, truncated = self.histories[(repository, path)]
        if max_commits is not None and len(commits) > max_commits:
            return commits[:max_commits], True
        return commits, truncated

    def get_commit(self, repository: str, commit: str) -> dict[str, Any]:
        return self.commits[(repository, commit)]

    def get_file(self, repository: str, path: str, ref: str) -> tuple[dict[str, Any], bytes]:
        return self.files[(repository, path, ref)]


def _search_item(repository: str, path: str, sha: str = "a" * 40) -> dict[str, Any]:
    return {
        "path": path,
        "sha": sha,
        "html_url": f"https://github.com/{repository}/blob/main/{path}",
        "repository": {"full_name": repository},
    }


def _commit(sha: str, timestamp: str) -> dict[str, Any]:
    return {"sha": sha, "commit": {"committer": {"date": timestamp}}}


def _file(blob: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    raw = json.dumps(payload, sort_keys=True).encode()
    return (
        {
            "sha": blob,
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(raw).decode(),
        },
        raw,
    )


def test_search_specs_freeze_five_concepts_over_two_exact_paths() -> None:
    specs = build_search_specs()

    assert len(specs) == 10
    assert {spec.query_id for spec in specs} == {"q1", "q2", "q3", "q4", "q5"}
    assert {spec.path for spec in specs} == {
        ".claude/settings.json",
        ".claude/settings.local.json",
    }
    assert all("path:.claude" in spec.api_query for spec in specs)


def test_discovery_keeps_only_exact_candidate_paths_and_deduplicates_locations() -> None:
    client = FakeClient()
    specs = build_search_specs()
    client.search_payloads[specs[0].api_query] = (
        [
            _search_item("org/one", ".claude/settings.json"),
            _search_item("org/one", "config/.claude/settings.json"),
        ],
        2,
        False,
    )
    client.search_payloads[specs[2].api_query] = (
        [_search_item("org/one", ".claude/settings.json")],
        1,
        False,
    )

    locations, queries, complete = discover_locations(client)

    assert complete is True
    assert len(locations) == 1
    assert locations[0]["repository_full_name"] == "org/one"
    assert locations[0]["path"] == ".claude/settings.json"
    assert len(locations[0]["discovered_by"]) == 2
    assert len(queries) == 10


def test_incomplete_or_capped_code_search_marks_discovery_incomplete() -> None:
    client = FakeClient()
    spec = build_search_specs()[0]
    client.search_payloads[spec.api_query] = ([], 1001, False)

    _, queries, complete = discover_locations(client)

    assert complete is False
    evidence = next(item for item in queries if item["api_query"] == spec.api_query)
    assert evidence["api_result_cap_reached"] is True


def test_transition_enumeration_performs_only_prelabel_mechanical_screening() -> None:
    client = FakeClient()
    repo = "org/project"
    path = ".claude/settings.json"
    candidate = "c" * 40
    baseline = "b" * 40
    client.histories[(repo, path)] = (
        [
            _commit(candidate, "2026-01-02T00:00:00Z"),
            _commit(baseline, "2026-01-01T00:00:00Z"),
        ],
        False,
    )
    client.commits[(repo, candidate)] = {"parents": [{"sha": baseline}]}
    client.files[(repo, path, baseline)] = _file(
        "1" * 40,
        {"permissions": {"defaultMode": "dontAsk", "allow": ["Bash(git status)"]}},
    )
    client.files[(repo, path, candidate)] = _file(
        "2" * 40,
        {"permissions": {"defaultMode": "dontAsk", "allow": ["Bash(git *)"]}},
    )
    locations = [
        {
            "repository_full_name": repo,
            "repository_url": f"https://github.com/{repo}",
            "path": path,
            "discovered_by": [{"query_id": "q1", "candidate_path": path}],
        }
    ]

    contract, _ = _load_cb01_contract()
    transitions, complete = enumerate_transitions(
        client, locations, contract, max_history_commits=None
    )

    assert complete is True
    assert len(transitions) == 1
    item = transitions[0]
    assert item["screening_status"] == "pending"
    assert item["manual_review_required"] is True
    assert item["permissions_changed"] is True
    assert item["exclusion_reasons"] == []
    assert item["baseline_blob"] == "1" * 40
    assert item["candidate_blob"] == "2" * 40


def test_unchanged_permissions_remain_pending_for_outside_projection_review() -> None:
    client = FakeClient()
    repo = "org/project"
    path = ".claude/settings.json"
    candidate = "c" * 40
    baseline = "b" * 40
    client.histories[(repo, path)] = (
        [_commit(candidate, "now"), _commit(baseline, "before")],
        False,
    )
    client.commits[(repo, candidate)] = {"parents": [{"sha": baseline}]}
    permissions = {"defaultMode": "dontAsk", "allow": ["Bash"]}
    client.files[(repo, path, baseline)] = _file("1" * 40, {"permissions": permissions, "x": 1})
    client.files[(repo, path, candidate)] = _file("2" * 40, {"permissions": permissions, "x": 2})
    locations = [
        {
            "repository_full_name": repo,
            "repository_url": f"https://github.com/{repo}",
            "path": path,
            "discovered_by": [],
        }
    ]

    contract, _ = _load_cb01_contract()
    transitions, _ = enumerate_transitions(client, locations, contract, max_history_commits=None)

    assert transitions[0]["screening_status"] == "pending"
    assert transitions[0]["permissions_changed"] is False
    assert transitions[0]["exclusion_reasons"] == []


def test_merge_transition_is_excluded_as_ambiguous() -> None:
    client = FakeClient()
    repo = "org/project"
    path = ".claude/settings.local.json"
    candidate = "c" * 40
    baseline = "b" * 40
    client.histories[(repo, path)] = (
        [_commit(candidate, "now"), _commit(baseline, "before")],
        False,
    )
    client.commits[(repo, candidate)] = {"parents": [{"sha": baseline}, {"sha": "d" * 40}]}
    client.files[(repo, path, baseline)] = _file("1" * 40, {"permissions": {"allow": []}})
    client.files[(repo, path, candidate)] = _file("2" * 40, {"permissions": {"allow": ["Bash"]}})
    locations = [
        {
            "repository_full_name": repo,
            "repository_url": f"https://github.com/{repo}",
            "path": path,
            "discovered_by": [],
        }
    ]

    contract, _ = _load_cb01_contract()
    transitions, _ = enumerate_transitions(client, locations, contract, max_history_commits=None)

    assert transitions[0]["screening_status"] == "excluded"
    assert "ambiguous_parent_transition" in transitions[0]["exclusion_reasons"]


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


def _screened_fixture(
    count: int,
    *,
    repos: list[str] | None = None,
    excluded_indices: set[int] | None = None,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    """Build a valid screened v1 ledger via CB01 derivation (synthetic)."""
    contract, contract_bytes = _load_cb01_contract()
    transitions: list[dict[str, Any]] = []
    for index in range(count):
        repo = repos[index % len(repos)] if repos else f"org/sel-{index:03d}"
        path = ".claude/settings.json" if index % 2 == 0 else ".claude/settings.local.json"
        url = f"https://github.com/{repo}"
        baseline = f"{index + 2000:040x}"
        candidate = f"{index + 6000:040x}"
        key = selection_key(url, baseline, candidate, path)
        transitions.append(
            {
                "transition_id": f"gh-{key[:20]}",
                "discovered_by": [{"query_id": "q1", "candidate_path": path}],
                "repository_full_name": repo,
                "repository_url": url,
                "path": path,
                "baseline_commit": baseline,
                "candidate_commit": candidate,
                "baseline_blob": f"{index + 100:040x}",
                "candidate_blob": f"{index + 200:040x}",
                "baseline_sha256": f"{index + 300:064x}",
                "candidate_sha256": f"{index + 400:064x}",
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
        "plan_version": PLAN_VERSION,
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "study_repository_commit": _SYNTHETIC_STUDY_COMMIT,
        "producer_id": "permitdiff-r3-canonical-public-discovery-v2",
        "source": "github-rest-code-search-and-commit-history",
        "generated_at": "2026-09-01T00:00:00Z",
        "discovery_complete": True,
        "limitations": ["synthetic selection fixture"],
        "queries": _queries_from_contract(contract),
        "discovered_location_count": 1,
        "transition_count": len(transitions),
        "transitions": copy.deepcopy(transitions),
    }
    raw_bytes = _canonical_bytes(raw)
    decisions_list: list[dict[str, Any]] = []
    excluded = excluded_indices or set()
    for index, item in enumerate(transitions):
        if index in excluded:
            decisions_list.append(
                {
                    "transition_id": item["transition_id"],
                    "repository_url": item["repository_url"],
                    "path": item["path"],
                    "baseline_commit": item["baseline_commit"],
                    "candidate_commit": item["candidate_commit"],
                    "permissions_changed": item["permissions_changed"],
                    "contamination_status": item["contamination_status"],
                    "decision": "excluded",
                    "exclusion_reasons": ["insufficient_public_semantics"],
                    "rationale": "synthetic exclusion",
                    "reviewer": "synthetic-reviewer",
                }
            )
        else:
            decisions_list.append(
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
                    "rationale": "synthetic eligibility",
                    "reviewer": "synthetic-reviewer",
                }
            )
    decisions = {
        "schema_version": "permitdiff.dev/r3-screening-decisions/v1",
        "plan_version": PLAN_VERSION,
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_ledger_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "generated_at": "2026-09-02T00:00:00Z",
        "instructions": "synthetic instructions",
        "decisions": decisions_list,
    }
    decisions_bytes = _canonical_bytes(decisions)
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    return screened, _canonical_bytes(screened), contract, contract_bytes


def test_selection_is_key_ordered_and_enforces_repository_cap() -> None:
    repos = ["org/a"] * 3 + [f"org/repo-{index}" for index in range(3, 20)]
    screened, screened_bytes, contract, contract_bytes = _screened_fixture(20, repos=repos)
    # All 20 eligible across 18 repos (org/a capped at 2 => cap 19, select 18).
    result = select_public_historical(screened, screened_bytes, contract, contract_bytes)

    assert result["target_case_count"] == 18
    assert result["maximum_cases_per_repository"] == 2
    assert result["minimum_viable_case_count"] == 12
    assert result["raw_eligible_count"] == 20
    assert result["cap_admissible_count"] == 19
    assert result["selected_case_count"] == 18
    assert result["shortfall"] == 0
    assert sum(item["repository_full_name"] == "org/a" for item in result["selected"]) <= 2
    selected_keys = [item["selection_key"] for item in result["selected"]]
    assert selected_keys == sorted(selected_keys)


def test_selection_refuses_tampered_screened_ledger() -> None:
    screened, _, contract, contract_bytes = _screened_fixture(12)
    tampered = copy.deepcopy(screened)
    tampered["transitions"][0]["selection_key"] = "0" * 64
    with pytest.raises(DiscoveryError, match=r"selection_key mismatch"):
        select_public_historical(tampered, _canonical_bytes(tampered), contract, contract_bytes)
    stale = copy.deepcopy(screened)
    with pytest.raises(DiscoveryError, match=r"does not match exact screened bytes"):
        select_public_historical(stale, b'{"tampered": true}', contract, contract_bytes)


def test_empty_discovery_ledger_conforms_to_machine_schema() -> None:
    client = FakeClient()
    contract, contract_bytes = _load_cb01_contract()

    ledger = build_ledger(client, contract, contract_bytes, _SYNTHETIC_STUDY_COMMIT)
    schema = json.loads(RAW_V2_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(ledger)
    assert ledger["schema_version"] == "permitdiff.dev/r3-public-discovery-ledger/v2"
    assert ledger["producer_id"] == "permitdiff-r3-canonical-public-discovery-v2"
    assert ledger["cb01_contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    assert ledger["study_repository_commit"] == _SYNTHETIC_STUDY_COMMIT
    assert ledger["discovery_complete"] is True
    assert ledger["queries"] and len(ledger["queries"]) == 10


def test_selection_output_conforms_to_machine_schema() -> None:
    screened, screened_bytes, contract, contract_bytes = _screened_fixture(12)
    result = select_public_historical(screened, screened_bytes, contract, contract_bytes)
    schema = json.loads(SELECTION_V2_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(result)
    assert result["target_case_count"] == 18
    assert result["maximum_cases_per_repository"] == 2
    assert result["minimum_viable_case_count"] == 12
    assert result["raw_eligible_count"] == 12
    assert result["cap_admissible_count"] == 12
    assert result["selected_case_count"] == 12
    assert result["shortfall"] == 6
    assert result["source_screened_ledger_sha256"] == hashlib.sha256(screened_bytes).hexdigest()


def test_get_json_preserves_wrapped_ssl_eof_for_retry(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise URLError(ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING"))

    monkeypatch.setattr(discovery, "urlopen", fake_urlopen)

    with pytest.raises(ssl.SSLEOFError):
        GitHubClient(None).get_json("/search/code", {"q": "query"})


def test_get_json_array_preserves_wrapped_ssl_eof_for_retry(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise URLError(ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING"))

    monkeypatch.setattr(discovery, "urlopen", fake_urlopen)

    with pytest.raises(ssl.SSLEOFError):
        GitHubClient(None)._get_json_array("/repos/org/project/commits", {"page": 1})


def test_get_json_still_wraps_nontransient_urlerror(monkeypatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise URLError("connection refused")

    monkeypatch.setattr(discovery, "urlopen", fake_urlopen)

    with pytest.raises(DiscoveryError, match="GitHub API request failed"):
        GitHubClient(None).get_json("/search/code", {"q": "query"})


def test_pre_exposed_control_is_excluded_and_never_selected() -> None:
    repository_url, baseline, candidate, path = next(iter(discovery.PRE_EXPOSED_CONTROLS))
    repository = repository_url.replace("https://github.com/", "")
    client = FakeClient()
    client.histories[(repository, path)] = (
        [
            _commit(candidate, "2026-09-02T00:00:00Z"),
            _commit(baseline, "2026-09-01T00:00:00Z"),
        ],
        False,
    )
    client.commits[(repository, candidate)] = {"parents": [{"sha": baseline}]}
    client.files[(repository, path, baseline)] = _file("1" * 40, {"permissions": {"allow": []}})
    client.files[(repository, path, candidate)] = _file(
        "2" * 40, {"permissions": {"allow": ["Bash"]}}
    )
    locations = [
        {
            "repository_full_name": repository,
            "repository_url": repository_url,
            "path": path,
            "discovered_by": [{"query_id": "q1", "candidate_path": path}],
        }
    ]

    contract, _ = _load_cb01_contract()
    transitions, complete = enumerate_transitions(
        client, locations, contract, max_history_commits=None
    )

    assert complete is True
    assert len(transitions) == 1
    item = transitions[0]
    assert item["contamination_status"] == "pre_exposed_engineering_control"
    assert item["screening_status"] == "excluded"
    assert "pre_exposed_engineering_control" in item["exclusion_reasons"]

    screened, _, contract, contract_bytes = _screened_fixture(12)
    tampered = copy.deepcopy(screened)
    tampered["transitions"][0]["contamination_status"] = "pre_exposed_engineering_control"
    with pytest.raises(DiscoveryError, match="cannot be contaminated"):
        select_public_historical(tampered, _canonical_bytes(tampered), contract, contract_bytes)

    # A screened ledger with no eligible cases is below minimum: refuse output.
    contract2, contract_bytes2 = _load_cb01_contract()
    raw_empty = {
        "schema_version": "permitdiff.dev/r3-public-discovery-ledger/v2",
        "plan_version": PLAN_VERSION,
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": hashlib.sha256(contract_bytes2).hexdigest(),
        "study_repository_commit": _SYNTHETIC_STUDY_COMMIT,
        "producer_id": "permitdiff-r3-canonical-public-discovery-v2",
        "source": "github-rest-code-search-and-commit-history",
        "generated_at": "2026-09-01T00:00:00Z",
        "discovery_complete": True,
        "limitations": ["synthetic"],
        "queries": _queries_from_contract(contract2),
        "discovered_location_count": 0,
        "transition_count": 0,
        "transitions": [],
    }
    raw_empty_bytes = _canonical_bytes(raw_empty)
    empty_screened = {
        "schema_version": "permitdiff.dev/r3-screened-discovery-ledger/v1",
        "plan_version": PLAN_VERSION,
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": hashlib.sha256(contract_bytes2).hexdigest(),
        "study_repository_commit": _SYNTHETIC_STUDY_COMMIT,
        "source_discovery_ledger_sha256": hashlib.sha256(raw_empty_bytes).hexdigest(),
        "source_screening_decisions_sha256": hashlib.sha256(b"{}").hexdigest(),
        "transition_count": 0,
        "transitions": [],
    }
    with pytest.raises(DiscoveryError, match=r"below frozen|minimum"):
        select_public_historical(
            empty_screened, _canonical_bytes(empty_screened), contract2, contract_bytes2
        )


def test_truncated_history_marks_incomplete_and_refuses_selection() -> None:
    client = FakeClient()
    specs = build_search_specs()
    client.search_payloads[specs[0].api_query] = (
        [_search_item("org/one", ".claude/settings.json")],
        1,
        False,
    )
    repo = "org/one"
    path = ".claude/settings.json"
    candidate = "c" * 40
    baseline = "b" * 40
    client.histories[(repo, path)] = (
        [
            _commit(candidate, "2026-01-02T00:00:00Z"),
            _commit(baseline, "2026-01-01T00:00:00Z"),
        ],
        True,
    )
    client.commits[(repo, candidate)] = {"parents": [{"sha": baseline}]}
    client.files[(repo, path, baseline)] = _file("1" * 40, {"permissions": {"allow": []}})
    client.files[(repo, path, candidate)] = _file("2" * 40, {"permissions": {"allow": ["Bash"]}})

    contract, contract_bytes = _load_cb01_contract()
    ledger = build_ledger(
        client, contract, contract_bytes, _SYNTHETIC_STUDY_COMMIT, max_history_commits=2
    )

    assert ledger["discovery_complete"] is False
    assert ledger["schema_version"] == "permitdiff.dev/r3-public-discovery-ledger/v2"
    # B4: selection consumes screened ledgers; a raw ledger is rejected.
    ledger_bytes = _canonical_bytes(ledger)
    with pytest.raises(DiscoveryError, match=r"unsupported screened ledger"):
        select_public_historical(ledger, ledger_bytes, contract, contract_bytes)


def test_enumerate_transitions_orders_by_selection_key() -> None:
    client = FakeClient()
    path = ".claude/settings.json"
    pairs = [
        ("org/zeta", "1" * 40, "a" * 40),
        ("org/alpha", "2" * 40, "b" * 40),
    ]
    locations = []
    for repo, baseline, candidate in pairs:
        client.histories[(repo, path)] = (
            [
                _commit(candidate, "2026-01-02T00:00:00Z"),
                _commit(baseline, "2026-01-01T00:00:00Z"),
            ],
            False,
        )
        client.commits[(repo, candidate)] = {"parents": [{"sha": baseline}]}
        client.files[(repo, path, baseline)] = _file("1" * 40, {"permissions": {"allow": []}})
        client.files[(repo, path, candidate)] = _file(
            "2" * 40, {"permissions": {"allow": ["Bash"]}}
        )
        locations.append(
            {
                "repository_full_name": repo,
                "repository_url": f"https://github.com/{repo}",
                "path": path,
                "discovered_by": [{"query_id": "q1", "candidate_path": path}],
            }
        )

    contract, _ = _load_cb01_contract()
    transitions, complete = enumerate_transitions(
        client, list(reversed(locations)), contract, max_history_commits=None
    )

    assert complete is True
    assert len(transitions) == 2
    keys = [item["selection_key"] for item in transitions]
    assert keys == sorted(keys)


def test_select_is_deterministic_across_runs() -> None:
    screened, screened_bytes, contract, contract_bytes = _screened_fixture(12)

    first = select_public_historical(screened, screened_bytes, contract, contract_bytes)
    second = select_public_historical(
        copy.deepcopy(screened), screened_bytes, contract, contract_bytes
    )

    assert first == second
    assert (
        first["source_screened_ledger_sha256"]
        == second["source_screened_ledger_sha256"]
        == hashlib.sha256(screened_bytes).hexdigest()
    )
    assert first["selected_case_count"] == 12
    assert first["shortfall"] == 6
    assert [c["rank"] for c in first["selected"]] == list(range(1, 13))


def test_selection_refuses_unresolved_screening() -> None:
    screened, _, contract, contract_bytes = _screened_fixture(12)
    tampered = copy.deepcopy(screened)
    tampered["transitions"][0]["screening_status"] = "pending"
    with pytest.raises(DiscoveryError, match=r"must never contain pending"):
        select_public_historical(tampered, _canonical_bytes(tampered), contract, contract_bytes)


def test_selection_rejects_unsupported_screening_status() -> None:
    screened, _, contract, contract_bytes = _screened_fixture(12)
    tampered = copy.deepcopy(screened)
    tampered["transitions"][0]["screening_status"] = "unknown-status"
    with pytest.raises(DiscoveryError, match=r"must never contain pending"):
        select_public_historical(tampered, _canonical_bytes(tampered), contract, contract_bytes)


@pytest.mark.parametrize(
    "field",
    [
        "baseline_blob",
        "candidate_blob",
        "baseline_sha256",
        "candidate_sha256",
    ],
)
def test_selection_rejects_eligible_without_provenance(field: str) -> None:
    screened, _, contract, contract_bytes = _screened_fixture(12)
    tampered = copy.deepcopy(screened)
    for item in tampered["transitions"]:
        if item["screening_status"] == "eligible":
            item[field] = None
            break
    with pytest.raises(DiscoveryError, match="lacks provenance"):
        select_public_historical(tampered, _canonical_bytes(tampered), contract, contract_bytes)


def test_b4_count_semantics_table() -> None:
    screened12, b12, c12, cb12 = _screened_fixture(12)
    sel12 = select_public_historical(screened12, b12, c12, cb12)
    assert (sel12["raw_eligible_count"], sel12["cap_admissible_count"]) == (12, 12)
    assert (sel12["selected_case_count"], sel12["shortfall"]) == (12, 6)

    screened17, b17, c17, cb17 = _screened_fixture(17)
    sel17 = select_public_historical(screened17, b17, c17, cb17)
    assert (sel17["selected_case_count"], sel17["shortfall"]) == (17, 1)

    screened18, b18, c18, cb18 = _screened_fixture(18)
    sel18 = select_public_historical(screened18, b18, c18, cb18)
    assert (sel18["selected_case_count"], sel18["shortfall"]) == (18, 0)

    screened25, b25, c25, cb25 = _screened_fixture(25)
    sel25 = select_public_historical(screened25, b25, c25, cb25)
    assert (sel25["selected_case_count"], sel25["shortfall"]) == (18, 0)
    assert [c["rank"] for c in sel25["selected"]] == list(range(1, 19))

    concentrated, bc, cc, cbc = _screened_fixture(30, repos=["org/concentrated"])
    with pytest.raises(DiscoveryError, match=r"below frozen|minimum"):
        select_public_historical(concentrated, bc, cc, cbc)


def test_b4_below_minimum_cli_creates_no_output(tmp_path) -> None:
    _, screened_bytes, _, _ = _screened_fixture(5)
    ledger_path = tmp_path / "screened.json"
    ledger_path.write_bytes(screened_bytes)
    output_path = tmp_path / "selection.json"
    assert (
        discovery.main(["select", "--ledger", str(ledger_path), "--output", str(output_path)]) == 1
    )
    assert not output_path.exists()


def test_select_cli_fails_before_writing_non_frozen_artifact(tmp_path) -> None:
    _, screened_bytes, _, _ = _screened_fixture(12)
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_bytes(screened_bytes)
    output_path = tmp_path / "selection.json"

    assert (
        discovery.main(
            [
                "select",
                "--ledger",
                str(ledger_path),
                "--output",
                str(output_path),
                "--target",
                "17",
            ]
        )
        == 1
    )
    assert not output_path.exists()

    assert (
        discovery.main(
            [
                "select",
                "--ledger",
                str(ledger_path),
                "--output",
                str(output_path),
                "--max-per-repository",
                "3",
            ]
        )
        == 1
    )
    assert not output_path.exists()


def test_b4_legacy_v1_selection_rejected() -> None:
    screened, screened_bytes, contract, contract_bytes = _screened_fixture(12)
    result = select_public_historical(screened, screened_bytes, contract, contract_bytes)
    assert "target_cases" not in result
    assert "eligible_case_count" not in result
    assert "source_ledger_sha256" not in result
    legacy = copy.deepcopy(result)
    legacy["schema_version"] = "permitdiff.dev/r3-public-selection/v1"
    with pytest.raises(cb01.CB01ConstructionError, match=r"unsupported public selection"):
        cb01.validate_selection_v2(legacy, contract, contract_bytes)
