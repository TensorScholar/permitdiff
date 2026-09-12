#!/usr/bin/env python3
"""Prepare and apply output-blind manual screening decisions for the R3 public ledger."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from scripts.discover_r3_benchmark_candidates import (
    FIXED_EXCLUSION_REASONS,
    LEDGER_SCHEMA_VERSION,
    PLAN_VERSION,
    PROTOCOL_VERSION,
    DiscoveryError,
    selection_key,
)

SCREENING_SCHEMA_VERSION = "permitdiff.dev/r3-screening-decisions/v1"


class ScreeningError(ValueError):
    """Raised when screening input violates the preregistered evidence contract."""


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScreeningError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScreeningError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScreeningError(f"{label} must contain a JSON object: {path}")
    return payload, raw


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _schema_error_path(error: ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _validate_schema(payload: dict[str, Any], schema_path: Path) -> None:
    schema, _ = _read_json_bytes(schema_path, label="screening schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ScreeningError(f"screening schema is invalid: {exc.message}") from exc
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(validator.iter_errors(payload), None)
    if error is not None:
        raise ScreeningError(
            f"screening schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _validate_ledger(ledger: Mapping[str, Any], *, require_complete: bool = True) -> None:
    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise ScreeningError("unsupported discovery ledger schema version")
    if ledger.get("plan_version") != PLAN_VERSION:
        raise ScreeningError("ledger plan version does not match the preregistered plan")
    if ledger.get("protocol_version") != PROTOCOL_VERSION:
        raise ScreeningError("ledger protocol version does not match the preregistered protocol")
    if require_complete and ledger.get("discovery_complete") is not True:
        raise ScreeningError("screening requires a complete discovery ledger")

    raw_transitions = ledger.get("transitions")
    if not isinstance(raw_transitions, list):
        raise ScreeningError("ledger transitions must be a list")
    if ledger.get("transition_count") != len(raw_transitions):
        raise ScreeningError("ledger transition_count does not match transitions")

    seen_ids: set[str] = set()
    for raw in raw_transitions:
        if not isinstance(raw, Mapping):
            raise ScreeningError("ledger contains a non-object transition")
        transition_id = raw.get("transition_id")
        if not isinstance(transition_id, str):
            raise ScreeningError("ledger transition has an invalid transition_id")
        if transition_id in seen_ids:
            raise ScreeningError(f"duplicate transition_id in ledger: {transition_id}")
        seen_ids.add(transition_id)

        expected_key = selection_key(
            str(raw.get("repository_url")),
            str(raw.get("baseline_commit")),
            str(raw.get("candidate_commit")),
            str(raw.get("path")),
        )
        if raw.get("selection_key") != expected_key:
            raise ScreeningError(f"selection key mismatch for {transition_id}")

        status = raw.get("screening_status")
        reasons = raw.get("exclusion_reasons")
        if status not in {"pending", "eligible", "excluded"}:
            raise ScreeningError(f"invalid screening_status for {transition_id}")
        if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
            raise ScreeningError(f"malformed exclusion_reasons for {transition_id}")
        unknown = set(reasons) - FIXED_EXCLUSION_REASONS
        if unknown:
            raise ScreeningError(
                f"transition {transition_id} uses non-preregistered exclusions: {sorted(unknown)}"
            )
        if status == "pending" and raw.get("manual_review_required") is not True:
            raise ScreeningError(f"pending transition {transition_id} must require manual review")
        if status != "pending" and raw.get("manual_review_required") is not False:
            raise ScreeningError(
                f"resolved transition {transition_id} cannot require manual review"
            )
        if status == "eligible" and reasons:
            raise ScreeningError(f"eligible transition {transition_id} cannot have exclusions")
        if status == "eligible" and raw.get("contamination_status") != "clean":
            raise ScreeningError(f"eligible transition {transition_id} cannot be contaminated")


def _decision_stub(transition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transition_id": transition["transition_id"],
        "repository_url": transition["repository_url"],
        "path": transition["path"],
        "baseline_commit": transition["baseline_commit"],
        "candidate_commit": transition["candidate_commit"],
        "permissions_changed": transition["permissions_changed"],
        "contamination_status": transition["contamination_status"],
        "decision": "pending",
        "exclusion_reasons": [],
        "rationale": None,
        "reviewer": None,
    }


def prepare_screening(ledger_path: Path) -> dict[str, Any]:
    """Create an output-blind worksheet for every manually pending transition."""

    ledger, ledger_bytes = _read_json_bytes(ledger_path, label="discovery ledger")
    _validate_ledger(ledger)
    raw_transitions = ledger["transitions"]
    pending = [
        _decision_stub(transition)
        for transition in raw_transitions
        if isinstance(transition, Mapping) and transition["screening_status"] == "pending"
    ]
    return {
        "schema_version": SCREENING_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "source_ledger_sha256": _sha256_bytes(ledger_bytes),
        "generated_at": _utc_now(),
        "instructions": (
            "Review without consulting PermitDiff output. Resolve every decision to eligible or "
            "excluded. Excluded decisions require one or more preregistered exclusion reasons."
        ),
        "decisions": pending,
    }


def _decision_metadata_matches(
    transition: Mapping[str, Any], decision: Mapping[str, Any]
) -> bool:
    fields = (
        "transition_id",
        "repository_url",
        "path",
        "baseline_commit",
        "candidate_commit",
        "permissions_changed",
        "contamination_status",
    )
    return all(transition.get(field) == decision.get(field) for field in fields)


def apply_screening(
    ledger_path: Path,
    decisions_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    """Apply a complete output-blind screening worksheet to a bound source ledger."""

    ledger, ledger_bytes = _read_json_bytes(ledger_path, label="discovery ledger")
    _validate_ledger(ledger)
    decisions, _ = _read_json_bytes(decisions_path, label="screening decisions")
    _validate_schema(decisions, schema_path)

    if decisions.get("schema_version") != SCREENING_SCHEMA_VERSION:
        raise ScreeningError("unsupported screening decisions schema version")
    if decisions.get("plan_version") != PLAN_VERSION:
        raise ScreeningError("screening decisions plan version mismatch")
    if decisions.get("protocol_version") != PROTOCOL_VERSION:
        raise ScreeningError("screening decisions protocol version mismatch")
    if decisions.get("source_ledger_sha256") != _sha256_bytes(ledger_bytes):
        raise ScreeningError("screening decisions are not bound to the supplied ledger bytes")

    raw_decisions = decisions.get("decisions")
    if not isinstance(raw_decisions, list):
        raise ScreeningError("screening decisions must be a list")

    by_id: dict[str, Mapping[str, Any]] = {}
    for raw in raw_decisions:
        if not isinstance(raw, Mapping):
            raise ScreeningError("screening decisions contain a non-object entry")
        transition_id = str(raw.get("transition_id"))
        if transition_id in by_id:
            raise ScreeningError(f"duplicate screening decision for {transition_id}")
        by_id[transition_id] = raw

    pending = {
        str(transition["transition_id"]): transition
        for transition in ledger["transitions"]
        if isinstance(transition, Mapping) and transition["screening_status"] == "pending"
    }
    missing = sorted(set(pending) - set(by_id))
    extra = sorted(set(by_id) - set(pending))
    if missing:
        raise ScreeningError(f"screening decisions are missing pending transitions: {missing}")
    if extra:
        raise ScreeningError(f"screening decisions contain non-pending transitions: {extra}")

    screened = copy.deepcopy(ledger)
    screened_by_id = {
        str(transition["transition_id"]): transition for transition in screened["transitions"]
    }
    eligible_count = 0
    excluded_count = 0
    for transition_id, source_transition in pending.items():
        decision = by_id[transition_id]
        if not _decision_metadata_matches(source_transition, decision):
            raise ScreeningError(f"screening decision metadata mismatch for {transition_id}")

        outcome = decision.get("decision")
        if outcome == "pending":
            raise ScreeningError(f"screening decision remains pending for {transition_id}")
        if outcome not in {"eligible", "excluded"}:
            raise ScreeningError(f"invalid screening decision for {transition_id}: {outcome!r}")

        target = screened_by_id[transition_id]
        if outcome == "eligible":
            if source_transition.get("contamination_status") != "clean":
                raise ScreeningError(f"contaminated transition cannot be eligible: {transition_id}")
            required_provenance = (
                "baseline_blob",
                "candidate_blob",
                "baseline_sha256",
                "candidate_sha256",
            )
            if any(source_transition.get(field) is None for field in required_provenance):
                raise ScreeningError(
                    f"eligible transition lacks immutable artifact provenance: {transition_id}"
                )
            target["screening_status"] = "eligible"
            target["exclusion_reasons"] = []
            eligible_count += 1
        else:
            reasons = decision.get("exclusion_reasons")
            if not isinstance(reasons, list) or not reasons:
                raise ScreeningError(
                    f"excluded transition requires an exclusion reason: {transition_id}"
                )
            unknown = set(str(reason) for reason in reasons) - FIXED_EXCLUSION_REASONS
            if unknown:
                raise ScreeningError(
                    f"transition {transition_id} uses non-preregistered exclusions: "
                    f"{sorted(unknown)}"
                )
            target["screening_status"] = "excluded"
            target["exclusion_reasons"] = sorted(set(str(reason) for reason in reasons))
            excluded_count += 1
        target["manual_review_required"] = False

    _validate_ledger(screened)
    if any(
        transition.get("screening_status") == "pending"
        for transition in screened["transitions"]
        if isinstance(transition, Mapping)
    ):
        raise ScreeningError("screened ledger still contains pending transitions")

    print(
        json.dumps(
            {
                "source_ledger_sha256": _sha256_bytes(ledger_bytes),
                "resolved_manual_decisions": len(pending),
                "eligible_manual_decisions": eligible_count,
                "excluded_manual_decisions": excluded_count,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return screened


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="create a manual screening worksheet")
    prepare.add_argument("--ledger", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)

    apply = subparsers.add_parser("apply", help="apply a completed screening worksheet")
    apply.add_argument("--ledger", type=Path, required=True)
    apply.add_argument("--decisions", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "r3-screening-decisions.schema.json",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            worksheet = prepare_screening(args.ledger)
            _write_json(args.output, worksheet)
            return 0
        screened = apply_screening(args.ledger, args.decisions, args.schema)
        _write_json(args.output, screened)
        return 0
    except (DiscoveryError, ScreeningError) as exc:
        print(f"R3 screening failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
