from __future__ import annotations

import json
import ssl
from http.client import IncompleteRead, RemoteDisconnected
from typing import Any

import scripts.discover_r3_public_benchmark_candidates as public_discovery
from scripts.discover_r3_benchmark_candidates import (
    DiscoveryError,
    GitHubClient,
    build_search_specs,
    selection_key,
)
from scripts.discover_r3_public_benchmark_candidates import PublicOnlyGitHubClient


def _item(repository: str, *, private: bool | None) -> dict[str, Any]:
    repo: dict[str, Any] = {"full_name": repository}
    if private is not None:
        repo["private"] = private
    return {
        "path": ".claude/settings.json",
        "sha": "a" * 40,
        "repository": repo,
    }


def test_public_only_client_excludes_private_results(monkeypatch) -> None:
    raw_items = [
        _item("public/example", private=False),
        _item("private/example", private=True),
    ]

    monkeypatch.setattr(
        GitHubClient,
        "search_code",
        lambda self, query: (raw_items, len(raw_items), False),
    )

    items, total_count, incomplete = PublicOnlyGitHubClient(None).search_code("query")

    assert total_count == 2
    assert incomplete is False
    assert [item["repository"]["full_name"] for item in items] == ["public/example"]


def test_public_only_client_fails_closed_when_visibility_is_missing(monkeypatch) -> None:
    raw_items = [
        _item("public/example", private=False),
        _item("unknown/example", private=None),
    ]

    monkeypatch.setattr(
        GitHubClient,
        "search_code",
        lambda self, query: (raw_items, len(raw_items), False),
    )

    items, total_count, incomplete = PublicOnlyGitHubClient(None).search_code("query")

    assert total_count == 2
    assert incomplete is True
    assert [item["repository"]["full_name"] for item in items] == ["public/example"]


def test_existing_incomplete_search_state_is_preserved(monkeypatch) -> None:
    raw_items = [_item("public/example", private=False)]

    monkeypatch.setattr(
        GitHubClient,
        "search_code",
        lambda self, query: (raw_items, 1, True),
    )

    items, _, incomplete = PublicOnlyGitHubClient(None).search_code("query")

    assert len(items) == 1
    assert incomplete is True


def test_explicit_http_429_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise DiscoveryError(
                "GitHub API HTTP 429 for https://api.github.com/example: "
                '{"message":"try again in 0.25s"}'
            )
        return {"ok": True}

    monkeypatch.setattr(GitHubClient, "get_json", fake_get_json)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client.get_json("/repos/example/project", {"page": 3})

    assert result == {"ok": True}
    assert calls == [
        ("/repos/example/project", {"page": 3}),
        ("/repos/example/project", {"page": 3}),
    ]
    assert sleeps == [60.0]


def test_repeated_http_429_uses_bounded_exponential_backoff(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) <= 3:
            raise DiscoveryError(
                "GitHub API HTTP 429 for https://api.github.com/example: "
                '{"message":"try again in 0.25s"}'
            )
        return {"ok": True}

    monkeypatch.setattr(GitHubClient, "get_json", fake_get_json)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client.get_json("/repos/example/project", {"page": 3})

    assert result == {"ok": True}
    assert len(calls) == 4
    assert sleeps == [60.0, 120.0, 240.0]


def test_incomplete_read_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise IncompleteRead(b"partial", 10)
        return {"ok": True}

    monkeypatch.setattr(GitHubClient, "get_json", fake_get_json)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client.get_json("/repos/example/project", {"page": 4})

    assert result == {"ok": True}
    assert calls == [
        ("/repos/example/project", {"page": 4}),
        ("/repos/example/project", {"page": 4}),
    ]
    assert sleeps == [1.0]


def test_remote_disconnect_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []
    clock = iter([100.0, 101.0])

    def fake_get_json(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise RemoteDisconnected("remote end closed connection without response")
        return {"ok": True}

    monkeypatch.setattr(GitHubClient, "get_json", fake_get_json)
    monkeypatch.setattr(public_discovery.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client.get_json("/search/code", {"q": "query", "page": 7})

    assert result == {"ok": True}
    assert calls == [
        ("/search/code", {"q": "query", "page": 7}),
        ("/search/code", {"q": "query", "page": 7}),
    ]
    assert sleeps == [1.0, 11.0]


def test_ssl_eof_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING")
        return {"ok": True}

    monkeypatch.setattr(GitHubClient, "get_json", fake_get_json)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client.get_json("/repos/example/project", {"page": 4})

    assert result == {"ok": True}
    assert calls == [
        ("/repos/example/project", {"page": 4}),
        ("/repos/example/project", {"page": 4}),
    ]
    assert sleeps == [1.0]


def test_ssl_eof_array_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json_array(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING")
        return [{"sha": "a" * 40}]

    monkeypatch.setattr(GitHubClient, "_get_json_array", fake_get_json_array)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client._get_json_array("/repos/example/project/commits", {"page": 2})

    assert result == [{"sha": "a" * 40}]
    assert calls == [
        ("/repos/example/project/commits", {"page": 2}),
        ("/repos/example/project/commits", {"page": 2}),
    ]
    assert sleeps == [1.0]


def test_incomplete_array_read_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json_array(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise IncompleteRead(b"partial", 10)
        return [{"sha": "a" * 40}]

    monkeypatch.setattr(GitHubClient, "_get_json_array", fake_get_json_array)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client._get_json_array("/repos/example/project/commits", {"page": 2})

    assert result == [{"sha": "a" * 40}]
    assert calls == [
        ("/repos/example/project/commits", {"page": 2}),
        ("/repos/example/project/commits", {"page": 2}),
    ]
    assert sleeps == [1.0]


def test_remote_disconnect_array_is_retried_without_changing_request(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    sleeps: list[float] = []

    def fake_get_json_array(self, endpoint, params=None):
        calls.append((endpoint, params))
        if len(calls) == 1:
            raise RemoteDisconnected("remote end closed connection without response")
        return [{"sha": "a" * 40}]

    monkeypatch.setattr(GitHubClient, "_get_json_array", fake_get_json_array)
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    result = client._get_json_array("/repos/example/project/commits", {"page": 2})

    assert result == [{"sha": "a" * 40}]
    assert calls == [
        ("/repos/example/project/commits", {"page": 2}),
        ("/repos/example/project/commits", {"page": 2}),
    ]
    assert sleeps == [1.0]


def test_code_search_requests_are_paced(monkeypatch) -> None:
    sleeps: list[float] = []
    clock = iter([100.0, 102.0])

    monkeypatch.setattr(GitHubClient, "get_json", lambda self, endpoint, params=None: {})
    monkeypatch.setattr(public_discovery.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    client.get_json("/search/code", {"q": "first"})
    client.get_json("/search/code", {"q": "second"})

    assert sleeps == [10.0]


def test_history_listing_primes_commit_metadata_cache(monkeypatch) -> None:
    commit = {
        "sha": "a" * 40,
        "parents": [{"sha": "b" * 40}],
        "commit": {"committer": {"date": "2026-09-01T00:00:00Z"}},
    }

    monkeypatch.setattr(
        GitHubClient,
        "list_path_commits",
        lambda self, repository, path, max_commits=None: ([commit], False),
    )

    def unexpected_get_commit(self, repository, sha):
        raise AssertionError("cached history metadata should avoid a second API request")

    monkeypatch.setattr(GitHubClient, "get_commit", unexpected_get_commit)

    client = PublicOnlyGitHubClient(None)
    commits, truncated = client.list_path_commits("public/example", ".claude/settings.json")
    resolved = client.get_commit("public/example", "a" * 40)

    assert commits == [commit]
    assert truncated is False
    assert resolved == commit
    assert client._commit_cache_hits == 1
    assert client._commit_cache_misses == 0


def test_file_bytes_are_cached_by_exact_repository_path_and_ref(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []
    result = ({"sha": "c" * 40, "type": "file"}, b'{"permissions": {}}')

    def fake_get_file(self, repository, path, ref):
        calls.append((repository, path, ref))
        return result

    monkeypatch.setattr(GitHubClient, "get_file", fake_get_file)

    client = PublicOnlyGitHubClient(None)
    first = client.get_file("public/example", ".claude/settings.json", "a" * 40)
    second = client.get_file("public/example", ".claude/settings.json", "a" * 40)

    assert first == result
    assert second == result
    assert calls == [("public/example", ".claude/settings.json", "a" * 40)]
    assert client._file_cache_hits == 1
    assert client._file_cache_misses == 1


def test_progress_snapshot_is_atomic_noncanonical_and_token_free(tmp_path) -> None:
    progress_path = tmp_path / "discovery-progress.json"
    secret = "secret-token-must-not-appear"
    client = PublicOnlyGitHubClient(secret, progress_path=progress_path)

    client.finish("complete", transition_count=7)

    payload = json.loads(progress_path.read_text(encoding="utf-8"))
    raw = progress_path.read_text(encoding="utf-8")
    assert payload["schema_version"] == "permitdiff.dev/r3-discovery-progress/v1"
    assert payload["status"] == "complete"
    assert payload["last_event"]["event"] == "run_finished"
    assert payload["last_event"]["transition_count"] == 7
    assert secret not in raw
    assert not progress_path.with_name(progress_path.name + ".tmp").exists()


def test_public_search_forwards_frozen_query_unchanged(monkeypatch) -> None:
    seen: list[str] = []

    def fake_search_code(self, query: str):
        seen.append(query)
        return ([_item("public/example", private=False)], 1, False)

    monkeypatch.setattr(GitHubClient, "search_code", fake_search_code)

    client = PublicOnlyGitHubClient(None)
    specs = build_search_specs()
    for spec in specs:
        items, total_count, incomplete = client.search_code(spec.api_query)
        assert total_count == 1
        assert incomplete is False
        assert [item["repository"]["full_name"] for item in items] == ["public/example"]

    assert seen == [spec.api_query for spec in specs]


def test_public_select_cli_fails_before_writing_non_frozen_artifact(tmp_path) -> None:
    repository_url = "https://github.com/org/a"
    path = ".claude/settings.json"
    baseline = "1" * 40
    candidate = "a" * 40
    key = selection_key(repository_url, baseline, candidate, path)
    ledger = {
        "schema_version": "permitdiff.dev/r3-discovery-ledger/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "discovery_complete": True,
        "transitions": [
            {
                "transition_id": f"gh-{key[:20]}",
                "repository_full_name": "org/a",
                "repository_url": repository_url,
                "path": path,
                "baseline_commit": baseline,
                "candidate_commit": candidate,
                "baseline_blob": "1" * 40,
                "candidate_blob": "2" * 40,
                "baseline_sha256": "3" * 64,
                "candidate_sha256": "4" * 64,
                "selection_key": key,
                "screening_status": "eligible",
                "exclusion_reasons": [],
                "contamination_status": "clean",
            }
        ],
    }
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    output_path = tmp_path / "selection.json"

    assert (
        public_discovery.main(
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
