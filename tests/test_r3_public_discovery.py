from __future__ import annotations

from typing import Any

import scripts.discover_r3_public_benchmark_candidates as public_discovery
from scripts.discover_r3_benchmark_candidates import DiscoveryError, GitHubClient
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
                'GitHub API HTTP 429 for https://api.github.com/example: '
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
    assert sleeps == [1.25]


def test_code_search_requests_are_paced(monkeypatch) -> None:
    sleeps: list[float] = []
    clock = iter([100.0, 102.0])

    monkeypatch.setattr(GitHubClient, "get_json", lambda self, endpoint, params=None: {})
    monkeypatch.setattr(public_discovery.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(public_discovery.time, "sleep", sleeps.append)

    client = PublicOnlyGitHubClient(None)
    client.get_json("/search/code", {"q": "first"})
    client.get_json("/search/code", {"q": "second"})

    assert sleeps == [5.0]
