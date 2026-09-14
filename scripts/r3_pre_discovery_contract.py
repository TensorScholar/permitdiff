#!/usr/bin/env python3
"""Enforce PermitDiff R3 pre-discovery construction rules without running PermitDiff."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TARGET_CASES = 18
MINIMUM_CASES = 12
MAX_CASES_PER_REPOSITORY = 2

FAILURE_REASONS = frozenset(
    {
        "UNAVAILABLE_PROVENANCE",
        "CORRUPTED_ARTIFACT",
        "BROKEN_MATERIALIZATION",
        "DOCUMENTATION_SNAPSHOT_FAILURE",
        "INVALID_REVIEW_PACKET",
        "SCENARIO_EVIDENCE_INTEGRITY_FAILURE",
        "OTHER_PRE_EXECUTION_INTEGRITY_FAILURE",
    }
)


class PreDiscoveryContractError(ValueError):
    """Raised when frozen R3 construction rules are violated."""


def natural_corpus_disposition(eligible_count: int) -> str:
    """Return the exact preregistered action for an eligible natural-case count."""

    if isinstance(eligible_count, bool) or not isinstance(eligible_count, int):
        raise PreDiscoveryContractError("eligible_count must be an integer")
    if eligible_count < 0:
        raise PreDiscoveryContractError("eligible_count must be non-negative")
    if eligible_count >= TARGET_CASES:
        return "SELECT_EXACTLY_TARGET"
    if eligible_count >= MINIMUM_CASES:
        return "SELECT_ALL_ELIGIBLE_AND_REPORT_PREDECLARED_SHORTFALL"
    return "ABORT_CONSTRUCTION_PROTOCOL_AMENDMENT_REQUIRED"


def selected_case_failure_disposition(reason: str) -> str:
    """Fail the current corpus version for every frozen selected-case failure class."""

    if reason not in FAILURE_REASONS:
        raise PreDiscoveryContractError(f"unknown selected-case failure reason: {reason}")
    return "ABORT_CURRENT_CORPUS_VERSION_NO_REPLACEMENT"


def validate_selection_shape(selection: Mapping[str, Any]) -> str:
    """Validate the frozen target/cap/minimum invariants on one selection artifact."""

    if selection.get("target_cases") != TARGET_CASES:
        raise PreDiscoveryContractError("R3 target case count must remain exactly 18")
    if selection.get("max_cases_per_repository") != MAX_CASES_PER_REPOSITORY:
        raise PreDiscoveryContractError("R3 per-repository cap must remain exactly 2")
    eligible = selection.get("eligible_case_count")
    selected = selection.get("selected_case_count")
    shortfall = selection.get("shortfall")
    if isinstance(eligible, bool) or not isinstance(eligible, int) or eligible < 0:
        raise PreDiscoveryContractError("selection eligible_case_count is invalid")
    if isinstance(selected, bool) or not isinstance(selected, int) or selected < 0:
        raise PreDiscoveryContractError("selection selected_case_count is invalid")
    if shortfall != max(0, TARGET_CASES - selected):
        raise PreDiscoveryContractError("selection shortfall is inconsistent")

    disposition = natural_corpus_disposition(eligible)
    expected_selected = min(eligible, TARGET_CASES)
    if selected != expected_selected:
        raise PreDiscoveryContractError(
            "selection count "
            f"{selected} does not equal frozen deterministic count {expected_selected}"
        )
    if disposition == "ABORT_CONSTRUCTION_PROTOCOL_AMENDMENT_REQUIRED":
        raise PreDiscoveryContractError(
            f"eligible natural pool {eligible} is below frozen minimum {MINIMUM_CASES}; "
            "abort this construction attempt before materialization/adjudication"
        )
    return disposition


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    count = subparsers.add_parser("count", help="evaluate one eligible-count disposition")
    count.add_argument("eligible_count", type=int)

    selection = subparsers.add_parser("selection", help="validate a public-selection artifact")
    selection.add_argument("path", type=Path)

    failure = subparsers.add_parser("failure", help="resolve a selected-case failure")
    failure.add_argument("reason", choices=sorted(FAILURE_REASONS))

    args = parser.parse_args()
    if args.command == "count":
        print(natural_corpus_disposition(args.eligible_count))
        return 0
    if args.command == "failure":
        print(selected_case_failure_disposition(args.reason))
        return 0

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PreDiscoveryContractError("selection must be a JSON object")
    print(validate_selection_shape(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
