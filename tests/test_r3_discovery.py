from __future__ import annotations

import base64
import copy
import json
import ssl
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from jsonschema import Draft202012Validator
import scripts.discover_r3_benchmark_candidates as discovery
from scripts.discover_r3_benchmark_candidates import (
    LEDGER_SCHEMA_VERSION,
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
    transitions: list[dict[str, Any]] = []
    for index in range(3):
        transitions.append(
            _eligible_transition(
                "org/a", f"{index + 1:040x}", f"{index + 1001:040x}"
            )
        )
    for index in range(3, 20):
        transitions.append(
            _eligible_transition(
                f"org/repo-{index}", f"{index + 1:040x}", f"{index + 1001:040x}"
            )
        )
    transitions.append(
        _eligible_transition("org/c", "5" * 40, "e" * 40, status="excluded")
    )

    result = select_public_historical(_ledger(copy.deepcopy(transitions)))

    assert result["target_cases"] == 18
    assert result["max_cases_per_repository"] == 2
    assert result["eligible_case_count"] == 20
    assert result["selected_case_count"] == 18
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
    result = select_public_historical(_ledger([transition]))
    schema = json.loads(SELECTION_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(result)
    assert result["target_cases"] == 18
    assert result["max_cases_per_repository"] == 2
    assert result["selected_case_count"] == 1
    assert result["shortfall"] == 17


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
    client.files[(repository, path, baseline)] = _file(
        "1" * 40, {"permissions": {"allow": []}}
    )
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

    transitions, complete = enumerate_transitions(client, locations, max_history_commits=None)

    assert complete is True
    assert len(transitions) == 1
    item = transitions[0]
    assert item["contamination_status"] == "pre_exposed_engineering_control"
    assert item["screening_status"] == "excluded"
    assert "pre_exposed_engineering_control" in item["exclusion_reasons"]

    tampered = copy.deepcopy(item)
    tampered["screening_status"] = "eligible"
    tampered["exclusion_reasons"] = []
    with pytest.raises(DiscoveryError, match="cannot be contaminated"):
        select_public_historical(_ledger([tampered]))

    result = select_public_historical(
        _ledger([copy.deepcopy(item)]), target=18, max_per_repository=2
    )
    assert result["eligible_case_count"] == 0
    assert result["selected_case_count"] == 0
    assert result["shortfall"] == 18


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
    client.files[(repo, path, baseline)] = _file(
        "1" * 40, {"permissions": {"allow": []}}
    )
    client.files[(repo, path, candidate)] = _file(
        "2" * 40, {"permissions": {"allow": ["Bash"]}}
    )

    ledger = build_ledger(client, max_history_commits=2)

    assert ledger["discovery_complete"] is False
    with pytest.raises(DiscoveryError, match="incomplete discovery ledger"):
        select_public_historical(ledger)


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
        client.files[(repo, path, baseline)] = _file(
            "1" * 40, {"permissions": {"allow": []}}
        )
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

    transitions, complete = enumerate_transitions(
        client, list(reversed(locations)), max_history_commits=None
    )

    assert complete is True
    assert len(transitions) == 2
    keys = [item["selection_key"] for item in transitions]
    assert keys == sorted(keys)


def test_select_is_deterministic_across_runs() -> None:
    transitions = [
        _eligible_transition(
            "org/a" if index < 2 else f"org/repo-{index}",
            f"{index + 1:040x}",
            f"{index + 1001:040x}",
        )
        for index in range(5)
    ]

    first = select_public_historical(_ledger(copy.deepcopy(transitions)))
    second = select_public_historical(_ledger(copy.deepcopy(transitions)))

    assert first == second
    assert first["source_ledger_sha256"] == second["source_ledger_sha256"]
    assert first["selected_case_count"] == 5
    assert first["shortfall"] == 13


def test_selection_refuses_unresolved_screening() -> None:
    eligible = _eligible_transition("org/a", "1" * 40, "a" * 40)
    pending = _eligible_transition("org/b", "2" * 40, "b" * 40)
    pending["screening_status"] = "pending"
    pending["manual_review_required"] = True

    with pytest.raises(DiscoveryError, match="unresolved screening"):
        select_public_historical(_ledger([eligible, pending]))


def test_selection_rejects_unsupported_screening_status() -> None:
    transition = _eligible_transition("org/a", "1" * 40, "a" * 40)
    transition["screening_status"] = "unknown-status"

    with pytest.raises(DiscoveryError, match="unsupported screening_status"):
        select_public_historical(_ledger([transition]))


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
    transition = _eligible_transition("org/a", "1" * 40, "a" * 40)
    transition[field] = None

    with pytest.raises(DiscoveryError, match="immutable artifact provenance"):
        select_public_historical(_ledger([transition]))


def test_selection_rejects_non_frozen_parameters() -> None:
    transition = _eligible_transition("org/a", "1" * 40, "a" * 40)

    with pytest.raises(DiscoveryError, match="target must remain exactly 18"):
        select_public_historical(
            _ledger([copy.deepcopy(transition)]),
            target=17,
            max_per_repository=2,
        )
    with pytest.raises(DiscoveryError, match="per-repository cap must remain exactly 2"):
        select_public_historical(
            _ledger([copy.deepcopy(transition)]),
            target=18,
            max_per_repository=3,
        )


def test_select_cli_fails_before_writing_non_frozen_artifact(tmp_path) -> None:
    transition = _eligible_transition("org/a", "1" * 40, "a" * 40)
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(_ledger([transition]), indent=2) + "\n", encoding="utf-8"
    )
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
