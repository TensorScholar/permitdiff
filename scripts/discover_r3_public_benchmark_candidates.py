#!/usr/bin/env python3
"""Public-only entrypoint for preregistered R3 benchmark discovery.

Authenticated GitHub code search can expose repositories visible to the supplied token.
The R3 protocol admits only public historical sources, so this entrypoint filters search
results to repositories that explicitly report ``private: false`` before any location or
transition enters the discovery ledger. Missing visibility metadata fails the discovery
frame closed by marking the corresponding search incomplete.

Live collection also paces GitHub code-search requests, retries narrowly identified
transport failures, emits timestamped progress snapshots, and reuses immutable GitHub
responses within one run. These operational controls do not alter the frozen query text,
result ordering, screening rules, or selection semantics.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from typing import Any

from scripts.discover_r3_benchmark_candidates import (
    DiscoveryError,
    GitHubClient,
    _read_json,
    _resolve_token,
    _write_json,
    build_ledger,
    build_search_specs,
    select_public_historical,
)

_CODE_SEARCH_INTERVAL_SECONDS = 12.0
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_FALLBACK_SECONDS = 60.0
_RATE_LIMIT_MAX_SECONDS = 240.0
_RATE_LIMIT_DELAY = re.compile(r"try again in ([0-9]+(?:\.[0-9]+)?)s", re.IGNORECASE)
_TRANSIENT_READ_RETRIES = 3
_TRANSIENT_READ_RETRY_SECONDS = 1.0


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _retry_delay_seconds(error: DiscoveryError, *, retry_index: int) -> float | None:
    """Return a conservative bounded retry delay only for explicit GitHub HTTP 429 responses."""

    message = str(error)
    if "GitHub API HTTP 429" not in message and "HTTP Error 429" not in message:
        return None
    match = _RATE_LIMIT_DELAY.search(message)
    server_delay = (
        _RATE_LIMIT_FALLBACK_SECONDS
        if match is None
        else min(max(float(match.group(1)) + 1.0, 1.0), _RATE_LIMIT_MAX_SECONDS)
    )
    exponential_delay = min(
        _RATE_LIMIT_FALLBACK_SECONDS * (2**retry_index),
        _RATE_LIMIT_MAX_SECONDS,
    )
    return max(server_delay, exponential_delay)


class PublicOnlyGitHubClient(GitHubClient):
    """GitHub client that admits only explicitly public code-search results."""

    def __init__(self, token: str | None, *, progress_path: Path | None = None) -> None:
        super().__init__(token)
        self._last_code_search_request_at: float | None = None
        self._progress_path = progress_path
        self._started_at_epoch = time.time()
        self._search_query_total = len(build_search_specs())
        self._search_queries_started = 0
        self._search_queries_completed = 0
        self._history_locations_started = 0
        self._history_locations_completed = 0
        self._request_attempts = 0
        self._rate_limit_retries = 0
        self._transient_retries = 0
        self._commit_cache_hits = 0
        self._commit_cache_misses = 0
        self._file_cache_hits = 0
        self._file_cache_misses = 0
        self._history_commit_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._file_cache: dict[
            tuple[str, str, str], tuple[dict[str, Any], bytes]
        ] = {}
        self._last_progress: dict[str, Any] | None = None

    def _progress(self, event: str, **details: Any) -> None:
        record = {
            "timestamp": _utc_now(),
            "elapsed_seconds": round(max(0.0, time.time() - self._started_at_epoch), 3),
            "event": event,
            **details,
        }
        self._last_progress = record
        print(
            "[r3-discovery] " + json.dumps(record, sort_keys=True, ensure_ascii=False),
            file=sys.stderr,
            flush=True,
        )
        if self._progress_path is None:
            return
        snapshot = {
            "schema_version": "permitdiff.dev/r3-discovery-progress/v1",
            "status": details.get("status", "running"),
            "started_at": datetime.fromtimestamp(self._started_at_epoch, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "updated_at": record["timestamp"],
            "elapsed_seconds": record["elapsed_seconds"],
            "search_query_total": self._search_query_total,
            "search_queries_started": self._search_queries_started,
            "search_queries_completed": self._search_queries_completed,
            "history_locations_started": self._history_locations_started,
            "history_locations_completed": self._history_locations_completed,
            "request_attempts": self._request_attempts,
            "rate_limit_retries": self._rate_limit_retries,
            "transient_retries": self._transient_retries,
            "commit_cache_hits": self._commit_cache_hits,
            "commit_cache_misses": self._commit_cache_misses,
            "file_cache_hits": self._file_cache_hits,
            "file_cache_misses": self._file_cache_misses,
            "last_event": record,
        }
        path = self._progress_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def finish(self, status: str, **details: Any) -> None:
        """Persist a terminal progress state without changing discovery evidence."""

        self._progress("run_finished", status=status, **details)

    def _pace_code_search(self) -> None:
        now = time.monotonic()
        previous = self._last_code_search_request_at
        if previous is not None:
            remaining = _CODE_SEARCH_INTERVAL_SECONDS - (now - previous)
            if remaining > 0:
                self._progress("code_search_pacing", sleep_seconds=round(remaining, 3))
                time.sleep(remaining)
                now += remaining
        self._last_code_search_request_at = now

    def get_json(
        self, endpoint: str, params: Mapping[str, str | int] | None = None
    ) -> dict[str, Any]:
        """Retry bounded transport failures without changing endpoint or parameters."""

        rate_limit_attempts = 0
        read_attempts = 0
        while True:
            if endpoint == "/search/code":
                self._pace_code_search()
                self._progress(
                    "code_search_page_request",
                    page=None if params is None else params.get("page"),
                )
            self._request_attempts += 1
            try:
                return super().get_json(endpoint, params)
            except (IncompleteRead, RemoteDisconnected) as exc:
                if read_attempts == _TRANSIENT_READ_RETRIES:
                    self._progress(
                        "transient_retry_exhausted",
                        endpoint=endpoint,
                        error_type=type(exc).__name__,
                    )
                    raise
                read_attempts += 1
                self._transient_retries += 1
                self._progress(
                    "transient_retry",
                    endpoint=endpoint,
                    attempt=read_attempts,
                    sleep_seconds=_TRANSIENT_READ_RETRY_SECONDS,
                    error_type=type(exc).__name__,
                )
                time.sleep(_TRANSIENT_READ_RETRY_SECONDS)
            except DiscoveryError as exc:
                delay = _retry_delay_seconds(exc, retry_index=rate_limit_attempts)
                if delay is None or rate_limit_attempts == _RATE_LIMIT_RETRIES:
                    if delay is not None:
                        self._progress(
                            "rate_limit_retry_exhausted",
                            endpoint=endpoint,
                            attempts=rate_limit_attempts,
                        )
                    raise
                rate_limit_attempts += 1
                self._rate_limit_retries += 1
                self._progress(
                    "rate_limit_retry",
                    endpoint=endpoint,
                    attempt=rate_limit_attempts,
                    sleep_seconds=delay,
                )
                time.sleep(delay)

    def _get_json_array(
        self, endpoint: str, params: Mapping[str, str | int] | None = None
    ) -> list[dict[str, Any]]:
        """Retry bounded transport failures for paginated array endpoints."""

        rate_limit_attempts = 0
        read_attempts = 0
        while True:
            self._request_attempts += 1
            try:
                return super()._get_json_array(endpoint, params)
            except (IncompleteRead, RemoteDisconnected) as exc:
                if read_attempts == _TRANSIENT_READ_RETRIES:
                    self._progress(
                        "transient_retry_exhausted",
                        endpoint=endpoint,
                        error_type=type(exc).__name__,
                    )
                    raise
                read_attempts += 1
                self._transient_retries += 1
                self._progress(
                    "transient_retry",
                    endpoint=endpoint,
                    attempt=read_attempts,
                    sleep_seconds=_TRANSIENT_READ_RETRY_SECONDS,
                    error_type=type(exc).__name__,
                )
                time.sleep(_TRANSIENT_READ_RETRY_SECONDS)
            except DiscoveryError as exc:
                delay = _retry_delay_seconds(exc, retry_index=rate_limit_attempts)
                if delay is None or rate_limit_attempts == _RATE_LIMIT_RETRIES:
                    if delay is not None:
                        self._progress(
                            "rate_limit_retry_exhausted",
                            endpoint=endpoint,
                            attempts=rate_limit_attempts,
                        )
                    raise
                rate_limit_attempts += 1
                self._rate_limit_retries += 1
                self._progress(
                    "rate_limit_retry",
                    endpoint=endpoint,
                    attempt=rate_limit_attempts,
                    sleep_seconds=delay,
                )
                time.sleep(delay)

    def search_code(self, query: str) -> tuple[list[dict[str, Any]], int, bool]:
        self._search_queries_started += 1
        query_index = self._search_queries_started
        self._progress(
            "search_query_start",
            query_index=query_index,
            query_total=self._search_query_total,
            api_query=query,
        )
        items, total_count, incomplete = super().search_code(query)
        public_items: list[dict[str, Any]] = []
        visibility_unverified = False

        for item in items:
            repository = item.get("repository")
            if not isinstance(repository, Mapping):
                visibility_unverified = True
                continue
            private = repository.get("private")
            if not isinstance(private, bool):
                visibility_unverified = True
                continue
            if private is False:
                public_items.append(item)

        self._search_queries_completed += 1
        self._progress(
            "search_query_complete",
            query_index=query_index,
            query_total=self._search_query_total,
            reported_total_count=total_count,
            retrieved_count=len(items),
            public_retrieved_count=len(public_items),
            incomplete=incomplete or visibility_unverified,
        )

        # Private results are intentionally outside the preregistered public universe.
        # Missing visibility metadata is different: the source boundary cannot be proven,
        # so discovery fails closed instead of silently treating that result as public.
        return public_items, total_count, incomplete or visibility_unverified

    def list_path_commits(
        self, repository: str, path: str, *, max_commits: int | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        self._history_locations_started += 1
        location_index = self._history_locations_started
        self._progress(
            "history_location_start",
            location_index=location_index,
            repository=repository,
            path=path,
        )
        commits, truncated = super().list_path_commits(
            repository, path, max_commits=max_commits
        )
        for record in commits:
            sha = record.get("sha")
            parents = record.get("parents")
            if isinstance(sha, str) and len(sha) == 40 and isinstance(parents, list):
                self._history_commit_cache[(repository, sha)] = record
        self._history_locations_completed += 1
        self._progress(
            "history_location_complete",
            location_index=location_index,
            repository=repository,
            path=path,
            commit_count=len(commits),
            truncated=truncated,
        )
        return commits, truncated

    def get_commit(self, repository: str, commit: str) -> dict[str, Any]:
        cached = self._history_commit_cache.get((repository, commit))
        if cached is not None:
            self._commit_cache_hits += 1
            return cached
        self._commit_cache_misses += 1
        return super().get_commit(repository, commit)

    def get_file(self, repository: str, path: str, ref: str) -> tuple[dict[str, Any], bytes]:
        key = (repository, path, ref)
        cached = self._file_cache.get(key)
        if cached is not None:
            self._file_cache_hits += 1
            return cached
        self._file_cache_misses += 1
        result = super().get_file(repository, path, ref)
        self._file_cache[key] = result
        return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="collect the public-only GitHub ledger")
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument(
        "--progress-output",
        type=Path,
        help="write noncanonical operational progress snapshots for diagnostics",
    )
    discover.add_argument(
        "--max-history-commits",
        type=int,
        help="debug-only cap per path; any cap reached marks the ledger incomplete",
    )

    select = subparsers.add_parser("select", help="select from a fully screened ledger")
    select.add_argument("--ledger", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--target", type=int, default=18)
    select.add_argument("--max-per-repository", type=int, default=2)

    args = parser.parse_args(argv)
    client: PublicOnlyGitHubClient | None = None
    try:
        if args.command == "discover":
            if args.max_history_commits is not None and args.max_history_commits < 2:
                raise DiscoveryError("--max-history-commits must be at least 2")
            client = PublicOnlyGitHubClient(
                _resolve_token(), progress_path=args.progress_output
            )
            client._progress("run_started", output=str(args.output))
            ledger = build_ledger(
                client,
                max_history_commits=args.max_history_commits,
            )
            _write_json(args.output, ledger)
            if ledger["discovery_complete"] is not True:
                client.finish(
                    "incomplete",
                    discovered_location_count=ledger["discovered_location_count"],
                    transition_count=ledger["transition_count"],
                )
                print(
                    "R3 public discovery completed with an incomplete frame; "
                    "do not select cases from it.",
                    file=sys.stderr,
                )
                return 2
            client.finish(
                "complete",
                discovered_location_count=ledger["discovered_location_count"],
                transition_count=ledger["transition_count"],
            )
            return 0

        if args.target < 1 or args.max_per_repository < 1:
            raise DiscoveryError("selection target and per-repository cap must be positive")
        ledger = _read_json(args.ledger)
        result = select_public_historical(
            ledger,
            target=args.target,
            max_per_repository=args.max_per_repository,
        )
        _write_json(args.output, result)
        return 0
    except (DiscoveryError, IncompleteRead, RemoteDisconnected) as exc:
        if client is not None:
            client.finish("failed", error_type=type(exc).__name__, error=str(exc)[:500])
        print(f"R3 public discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
