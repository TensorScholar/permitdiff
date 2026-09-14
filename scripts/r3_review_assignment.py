#!/usr/bin/env python3
"""Deterministic R3 reviewer eligibility and condition assignment."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ASSIGNMENT_VERSION = "r3-condition-assignment-v1"
ASSIGNMENT_SCHEMA_VERSION = "permitdiff.dev/r3-condition-assignment/v1"
REVIEWER_PROTOCOL_VERSION = "r3-reviewer-protocol-v1"
CONDITIONS = ("PERMITDIFF_ASSISTED", "STRUCTURED_MANUAL", "SOURCE_TEXT_DIFF")


class AssignmentError(ValueError):
    """Raised when reviewer assignment cannot be frozen safely."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise AssignmentError(f"expected JSON object: {path}")
    return payload, raw


def _validate(payload: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def validate_roster(roster: dict[str, Any], case_ids: list[str]) -> list[str]:
    participants = roster.get("participants")
    if not isinstance(participants, list) or len(participants) != 3:
        raise AssignmentError("exactly three eligible participants are required")
    ids: list[str] = []
    seen: set[str] = set()
    case_set = set(case_ids)
    for raw in participants:
        if not isinstance(raw, dict):
            raise AssignmentError("participant entries must be objects")
        participant_id = raw.get("participant_id")
        if not isinstance(participant_id, str) or not participant_id:
            raise AssignmentError("participant_id is required")
        if participant_id in seen:
            raise AssignmentError(f"duplicate participant_id: {participant_id}")
        seen.add(participant_id)
        ids.append(participant_id)
        required_true = (
            "domain_familiarity_attested",
            "claude_settings_familiarity_attested",
            "training_completed",
        )
        if any(raw.get(field) is not True for field in required_true):
            raise AssignmentError(f"participant {participant_id} is not fully qualified")
        if raw.get("training_protocol_version") != "r3-reviewer-training-v1":
            raise AssignmentError(f"participant {participant_id} training version mismatch")
        if raw.get("product_behavior_contributor") is not False:
            raise AssignmentError(
                f"participant {participant_id} is a product-behavior contributor"
            )
        if raw.get("disqualifying_conflict") is not False:
            raise AssignmentError(f"participant {participant_id} has a disqualifying conflict")
        exposed = set(raw.get("case_specific_prior_exposure_case_ids", []))
        adjudicated = set(raw.get("case_specific_adjudication_case_ids", []))
        overlap = case_set & (exposed | adjudicated)
        if overlap:
            raise AssignmentError(
                f"participant {participant_id} has case-specific exposure: {sorted(overlap)}"
            )
    return ids


def build_assignment(
    *,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    roster: dict[str, Any],
    roster_bytes: bytes,
    reviewer_protocol_bytes: bytes,
) -> dict[str, Any]:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise AssignmentError("manifest must contain at least one case")
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or not all(
        isinstance(case_id, str) and case_id for case_id in case_ids
    ):
        raise AssignmentError("manifest contains invalid case ids")
    if len(set(case_ids)) != len(case_ids):
        raise AssignmentError("manifest contains duplicate case ids")

    participant_ids = validate_roster(roster, case_ids)
    manifest_sha = _sha256(manifest_bytes)
    roster_sha = _sha256(roster_bytes)
    protocol_sha = _sha256(reviewer_protocol_bytes)
    seed = _sha256(
        f"{ASSIGNMENT_VERSION}\n{manifest_sha}\n{roster_sha}".encode("utf-8")
    )

    ranked_cases = sorted(
        case_ids,
        key=lambda case_id: (_sha256(f"{seed}\ncase\n{case_id}".encode()), case_id),
    )
    ranked_participants = sorted(
        participant_ids,
        key=lambda participant_id: (
            _sha256(f"{seed}\nparticipant\n{participant_id}".encode()),
            participant_id,
        ),
    )
    case_rank = {case_id: index for index, case_id in enumerate(ranked_cases)}
    participant_rank = {
        participant_id: index for index, participant_id in enumerate(ranked_participants)
    }

    assignments: list[dict[str, Any]] = []
    for case_id in ranked_cases:
        for participant_id in ranked_participants:
            ci = (case_rank[case_id] + participant_rank[participant_id]) % len(CONDITIONS)
            assignments.append(
                {
                    "case_id": case_id,
                    "participant_id": participant_id,
                    "condition": CONDITIONS[ci],
                    "case_rank": case_rank[case_id],
                    "participant_rank": participant_rank[participant_id],
                }
            )

    result = {
        "schema_version": ASSIGNMENT_SCHEMA_VERSION,
        "assignment_version": ASSIGNMENT_VERSION,
        "source_manifest_sha256": manifest_sha,
        "participant_roster_sha256": roster_sha,
        "reviewer_protocol_sha256": protocol_sha,
        "assignment_seed": seed,
        "generated_before_evaluated_exposure": True,
        "participants": ranked_participants,
        "cases": ranked_cases,
        "assignments": assignments,
    }
    validate_balance(result)
    return result


def validate_balance(assignment: dict[str, Any]) -> None:
    rows = assignment.get("assignments")
    cases = assignment.get("cases")
    participants = assignment.get("participants")
    if not (
        isinstance(rows, list)
        and isinstance(cases, list)
        and isinstance(participants, list)
    ):
        raise AssignmentError("assignment is malformed")

    expected_cells = {
        (case_id, participant_id)
        for case_id in cases
        for participant_id in participants
    }
    seen_cells: set[tuple[str, str]] = set()
    by_case: dict[str, Counter[str]] = defaultdict(Counter)
    by_participant: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if not isinstance(row, dict):
            raise AssignmentError("assignment row must be an object")
        key = (row.get("case_id"), row.get("participant_id"))
        if key in seen_cells:
            raise AssignmentError(f"duplicate assignment cell: {key}")
        seen_cells.add(key)  # type: ignore[arg-type]
        condition = row.get("condition")
        if condition not in CONDITIONS:
            raise AssignmentError(f"invalid condition: {condition}")
        by_case[str(key[0])][str(condition)] += 1
        by_participant[str(key[1])][str(condition)] += 1
    if seen_cells != expected_cells:
        raise AssignmentError("assignment does not cover every case/participant cell exactly once")

    for counts in [*by_case.values(), *by_participant.values()]:
        values = [counts.get(condition, 0) for condition in CONDITIONS]
        if max(values) - min(values) > 1:
            raise AssignmentError("condition balance differs by more than one")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--reviewer-protocol", type=Path, required=True)
    parser.add_argument(
        "--roster-schema", type=Path, default=Path("docs/r3-reviewer-roster.schema.json")
    )
    parser.add_argument(
        "--assignment-schema",
        type=Path,
        default=Path("docs/r3-condition-assignment.schema.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest, manifest_bytes = _load_json(args.manifest)
    roster, roster_bytes = _load_json(args.roster)
    _validate(roster, args.roster_schema)
    reviewer_protocol, reviewer_protocol_bytes = _load_json(args.reviewer_protocol)
    if reviewer_protocol.get("protocol_version") != REVIEWER_PROTOCOL_VERSION:
        raise AssignmentError("reviewer protocol version mismatch")
    result = build_assignment(
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        roster=roster,
        roster_bytes=roster_bytes,
        reviewer_protocol_bytes=reviewer_protocol_bytes,
    )
    _validate(result, args.assignment_schema)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
