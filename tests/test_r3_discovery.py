from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from scripts.discover_r3_benchmark_candidates import (
    LEDGER_SCHEMA_VERSION,
    PLAN_VERSION,
    DiscoveryError,
    build_ledger,
    build_search_specs,
    discover_locations,
    enumerate_transitions,
    select_public_historical,
    selection_key,
)

ROOT = Path(__file__).resolve().parents[1]
LEDGER_SCHEMA = ROOT / "docs" / "r3-discovery-ledger.schema.json"
SELECTION_SCHEMA = ROOT / "docs" / "r3-public-selection.schema.json"


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

    transitions, complete = enumerate_transitions(client, locations, max_history_commits=None)

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

    transitions, _ = enumerate_transitions(client, locations, max_history_commits=None)

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

    transitions, _ = enumerate_transitions(client, locations, max_history_commits=None)

    assert transitions[0]["screening_status"] == "excluded"
    assert "ambiguous_parent_transition" in transitions[0]["exclusion_reasons"]


def _eligible_transition(
    repository: str, baseline: str, candidate: str, *, status: str = "eligible"
) -> dict[str, Any]:
    repository_url = f"https://github.com/{repository}"
    path = ".claude/settings.json"
    key = selection_key(repository_url, baseline, candidate, path)
    return {
        "transition_id": f"gh-{key[:20]}",
        "repository_full_name": repository,
        "repository_url": repository_url,
        "path": path,
        "baseline_commit": baseline,
        "candidate_commit": candidate,
        "baseline_blob": "1" * 40,
        "candidate_blob": "2" * 40,
        "baseline_sha256": "3" * 64,
        "candidate_sha256": "4" * 64,
        "selection_key": key,
        "screening_status": status,
        "exclusion_reasons": [] if status == "eligible" else ["insufficient_public_semantics"],
        "contamination_status": "clean",
    }


def _ledger(transitions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": "r3-benchmark-protocol-v1",
        "discovery_complete": True,
        "transitions": transitions,
    }


def test_selection_is_key_ordered_and_enforces_repository_cap() -> None:
    transitions = [
        _eligible_transition("org/a", "1" * 40, "a" * 40),
        _eligible_transition("org/a", "2" * 40, "b" * 40),
        _eligible_transition("org/a", "3" * 40, "c" * 40),
        _eligible_transition("org/b", "4" * 40, "d" * 40),
        _eligible_transition("org/c", "5" * 40, "e" * 40, status="excluded"),
    ]

    result = select_public_historical(
        _ledger(copy.deepcopy(transitions)), target=3, max_per_repository=2
    )

    assert result["selected_case_count"] == 3
    assert result["shortfall"] == 0
    assert sum(item["repository_full_name"] == "org/a" for item in result["selected"]) <= 2
    selected_keys = [item["selection_key"] for item in result["selected"]]
    assert selected_keys == sorted(selected_keys)
    assert all(item["repository_full_name"] != "org/c" for item in result["selected"])


def test_selection_refuses_incomplete_or_tampered_ledger() -> None:
    transition = _eligible_transition("org/a", "1" * 40, "a" * 40)
    incomplete = _ledger([copy.deepcopy(transition)])
    incomplete["discovery_complete"] = False

    with pytest.raises(DiscoveryError, match="incomplete discovery ledger"):
        select_public_historical(incomplete)

    tampered = _ledger([copy.deepcopy(transition)])
    tampered["transitions"][0]["selection_key"] = "0" * 64
    with pytest.raises(DiscoveryError, match="selection key mismatch"):
        select_public_historical(tampered)


def test_empty_discovery_ledger_conforms_to_machine_schema() -> None:
    client = FakeClient()

    ledger = build_ledger(client)
    schema = json.loads(LEDGER_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(ledger)
    assert ledger["discovery_complete"] is True
    assert ledger["queries"] and len(ledger["queries"]) == 10


def test_selection_output_conforms_to_machine_schema() -> None:
    transition = _eligible_transition("org/a", "1" * 40, "a" * 40)
    result = select_public_historical(_ledger([transition]), target=1, max_per_repository=2)
    schema = json.loads(SELECTION_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(result)
    assert result["selected_case_count"] == 1
