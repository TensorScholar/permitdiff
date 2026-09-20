#!/usr/bin/env python3
"""Prepare and apply output-blind manual screening decisions for the R3 public ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from scripts import r3_cb01_corpus_construction as _cb01
from scripts.discover_r3_benchmark_candidates import (
    PLAN_VERSION,
    PROTOCOL_VERSION,
    DiscoveryError,
)

SCREENING_SCHEMA_VERSION = "permitdiff.dev/r3-screening-decisions/v1"
DEFAULT_CB01_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)


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


def _load_contract_bytes(
    contract_path: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Load exact CB-01 contract bytes; hashing must use these exact bytes."""

    path = contract_path or DEFAULT_CB01_CONTRACT_PATH
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScreeningError(f"failed to read CB-01 contract {path}: {exc}") from exc
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScreeningError(f"CB-01 contract is not valid JSON: {path}: {exc}") from exc
    if not isinstance(contract, dict):
        raise ScreeningError(f"CB-01 contract must contain a JSON object: {path}")
    try:
        _cb01.validate_contract_binding(contract, raw)
    except _cb01.CB01ConstructionError as exc:
        raise ScreeningError(f"invalid CB-01 contract: {exc}") from exc
    return contract, raw


def _validate_raw_v2(
    ledger: Mapping[str, Any],
    ledger_bytes: bytes,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> None:
    """Validate a raw v2 ledger via the CB-01 single source of truth."""

    try:
        _cb01.validate_raw_ledger(ledger, ledger_bytes, contract, contract_bytes)
    except _cb01.CB01ConstructionError as exc:
        raise ScreeningError(str(exc)) from exc


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


def prepare_screening(
    ledger_path: Path, contract_path: Path | None = None
) -> dict[str, Any]:
    """Create an output-blind worksheet for every manually pending transition."""

    ledger, ledger_bytes = _read_json_bytes(ledger_path, label="discovery ledger")
    contract, contract_bytes = _load_contract_bytes(contract_path)
    _validate_raw_v2(ledger, ledger_bytes, contract, contract_bytes)
    if ledger.get("discovery_complete") is not True:
        raise ScreeningError("screening requires a complete discovery ledger")
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


def apply_screening(
    ledger_path: Path,
    decisions_path: Path,
    schema_path: Path,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    """Apply a complete output-blind screening worksheet to a bound source ledger.

    Packet B3: the screened ledger is deterministically derived via the CB-01
    single source of truth. Successful publication requires
    ``derive_screened_ledger``, not only ``validate_screened_ledger``.
    """

    ledger, ledger_bytes = _read_json_bytes(ledger_path, label="discovery ledger")
    decisions, decisions_bytes = _read_json_bytes(
        decisions_path, label="screening decisions"
    )
    _validate_schema(decisions, schema_path)
    contract, contract_bytes = _load_contract_bytes(contract_path)
    try:
        screened = _cb01.derive_screened_ledger(
            ledger, ledger_bytes, decisions, decisions_bytes, contract, contract_bytes
        )
    except _cb01.CB01ConstructionError as exc:
        raise ScreeningError(str(exc)) from exc

    eligible_count = sum(
        1
        for item in screened["transitions"]
        if isinstance(item, Mapping) and item.get("screening_status") == "eligible"
    )
    excluded_count = sum(
        1
        for item in screened["transitions"]
        if isinstance(item, Mapping) and item.get("screening_status") == "excluded"
    )
    print(
        json.dumps(
            {
                "source_ledger_sha256": _sha256_bytes(ledger_bytes),
                "resolved_manual_decisions": eligible_count + excluded_count,
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
    prepare.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="CB-01 contract file; defaults to the committed contract",
    )

    apply = subparsers.add_parser("apply", help="apply a completed screening worksheet")
    apply.add_argument("--ledger", type=Path, required=True)
    apply.add_argument("--decisions", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "r3-screening-decisions.schema.json",
    )
    apply.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="CB-01 contract file; defaults to the committed contract",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            worksheet = prepare_screening(args.ledger, args.contract)
            _write_json(args.output, worksheet)
            return 0
        screened = apply_screening(args.ledger, args.decisions, args.schema, args.contract)
        _write_json(args.output, screened)
        return 0
    except (DiscoveryError, ScreeningError) as exc:
        print(f"R3 screening failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
