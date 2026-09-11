#!/usr/bin/env python3
"""Public-only entrypoint for preregistered R3 benchmark discovery.

Authenticated GitHub code search can expose repositories visible to the supplied token.
The R3 protocol admits only public historical sources, so this entrypoint filters search
results to repositories that explicitly report ``private: false`` before any location or
transition enters the discovery ledger. Missing visibility metadata fails the discovery
frame closed by marking the corresponding search incomplete.

Live collection also paces GitHub code-search requests and retries explicit HTTP 429
responses plus narrowly identified transient read/disconnect failures. Those transport
controls do not alter the frozen query text, result ordering, or screening rules.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections.abc import Mapping, Sequence
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
    select_public_historical,
)

_CODE_SEARCH_INTERVAL_SECONDS = 12.0
_RATE_LIMIT_RETRIES = 4
_RATE_LIMIT_FALLBACK_SECONDS = 60.0
_RATE_LIMIT_MAX_SECONDS = 240.0
_RATE_LIMIT_DELAY = re.compile(r"try again in ([0-9]+(?:\.[0-9]+)?)s", re.IGNORECASE)
_TRANSIENT_READ_RETRIES = 3
_TRANSIENT_READ_RETRY_SECONDS = 1.0


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

    def __init__(self, token: str | None) -> None:
        super().__init__(token)
        self._last_code_search_request_at: float | None = None

    def _pace_code_search(self) -> None:
        now = time.monotonic()
        previous = self._last_code_search_request_at
        if previous is not None:
            remaining = _CODE_SEARCH_INTERVAL_SECONDS - (now - previous)
            if remaining > 0:
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
            try:
                return super().get_json(endpoint, params)
            except (IncompleteRead, RemoteDisconnected):
                if read_attempts == _TRANSIENT_READ_RETRIES:
                    raise
                read_attempts += 1
                time.sleep(_TRANSIENT_READ_RETRY_SECONDS)
            except DiscoveryError as exc:
                delay = _retry_delay_seconds(exc, retry_index=rate_limit_attempts)
                if delay is None or rate_limit_attempts == _RATE_LIMIT_RETRIES:
                    raise
                rate_limit_attempts += 1
                time.sleep(delay)

    def _get_json_array(
        self, endpoint: str, params: Mapping[str, str | int] | None = None
    ) -> list[dict[str, Any]]:
        """Retry bounded transport failures for paginated array endpoints."""

        rate_limit_attempts = 0
        read_attempts = 0
        while True:
            try:
                return super()._get_json_array(endpoint, params)
            except (IncompleteRead, RemoteDisconnected):
                if read_attempts == _TRANSIENT_READ_RETRIES:
                    raise
                read_attempts += 1
                time.sleep(_TRANSIENT_READ_RETRY_SECONDS)
            except DiscoveryError as exc:
                delay = _retry_delay_seconds(exc, retry_index=rate_limit_attempts)
                if delay is None or rate_limit_attempts == _RATE_LIMIT_RETRIES:
                    raise
                rate_limit_attempts += 1
                time.sleep(delay)

    def search_code(self, query: str) -> tuple[list[dict[str, Any]], int, bool]:
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

        # Private results are intentionally outside the preregistered public universe.
        # Missing visibility metadata is different: the source boundary cannot be proven,
        # so discovery fails closed instead of silently treating that result as public.
        return public_items, total_count, incomplete or visibility_unverified


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="collect the public-only GitHub ledger")
    discover.add_argument("--output", type=Path, required=True)
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
    try:
        if args.command == "discover":
            if args.max_history_commits is not None and args.max_history_commits < 2:
                raise DiscoveryError("--max-history-commits must be at least 2")
            ledger = build_ledger(
                PublicOnlyGitHubClient(_resolve_token()),
                max_history_commits=args.max_history_commits,
            )
            _write_json(args.output, ledger)
            if ledger["discovery_complete"] is not True:
                print(
                    "R3 public discovery completed with an incomplete frame; "
                    "do not select cases from it.",
                    file=sys.stderr,
                )
                return 2
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
    except DiscoveryError as exc:
        print(f"R3 public discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
