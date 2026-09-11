from __future__ import annotations

from typing import Any

from scripts.discover_r3_benchmark_candidates import GitHubClient
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
