#!/usr/bin/env python3
"""Public-only entrypoint for preregistered R3 benchmark discovery.

Authenticated GitHub code search can expose repositories visible to the supplied token.
The R3 protocol admits only public historical sources, so this entrypoint filters search
results to repositories that explicitly report ``private: false`` before any location or
transition enters the discovery ledger. Missing visibility metadata fails the discovery
frame closed by marking the corresponding search incomplete.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
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


class PublicOnlyGitHubClient(GitHubClient):
    """GitHub client that admits only explicitly public code-search results."""

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
                    "R3 public discovery completed with an incomplete frame; do not select cases from it.",
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
