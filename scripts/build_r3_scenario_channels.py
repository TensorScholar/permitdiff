#!/usr/bin/env python3
"""Prepare and validate output-blind R3 scenario-channel provenance evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from scripts.discover_r3_benchmark_candidates import PLAN_VERSION, PROTOCOL_VERSION
from scripts.materialize_r3_public_selection import MATERIALIZATION_V2_SCHEMA_VERSION


def _require_hex_field(value: Any, *, length: int, field: str) -> None:
    """Require a lowercase hex digest field (Packet C lineage/study binding)."""

    if (
        not isinstance(value, str)
        or len(value) != length
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ScenarioChannelError(f"materialization has an invalid {field}")

SCENARIO_CHANNEL_SET_SCHEMA_VERSION = "permitdiff.dev/r3-scenario-channel-set/v1"
MEASUREMENT_CONTRACT_VERSION = "r3-exploratory-measurement-contract-v2"

_PRIMARY_ADMISSIBLE_PROVENANCE = {"PREEXISTING_PROJECT", "INDEPENDENT_BLIND"}
_DIAGNOSTIC_ONLY_PROVENANCE = {"DIAGNOSTIC_ANSWER_INFORMED", "PRODUCT_GENERATED"}
_VALID_PROVENANCE = _PRIMARY_ADMISSIBLE_PROVENANCE | _DIAGNOSTIC_ONLY_PROVENANCE
_ABSENCE_REASON = "NO_PRIMARY_ADMISSIBLE_SCENARIO_SET"


class ScenarioChannelError(ValueError):
    """Raised when R3 scenario-channel evidence violates the frozen provenance contract."""


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScenarioChannelError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScenarioChannelError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScenarioChannelError(f"{label} must contain a JSON object: {path}")
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
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _validate_schema(payload: dict[str, Any], schema_path: Path, *, label: str) -> None:
    schema, _ = _read_json_object_bytes(schema_path, label=f"{label} schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ScenarioChannelError(f"{label} schema is invalid: {exc.message}") from exc
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        None,
    )
    if error is not None:
        raise ScenarioChannelError(
            f"{label} schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _validate_materialization(
    materialization: Mapping[str, Any], materialization_schema_path: Path
) -> list[Mapping[str, Any]]:
    _validate_schema(dict(materialization), materialization_schema_path, label="materialization")
    if materialization.get("schema_version") != MATERIALIZATION_V2_SCHEMA_VERSION:
        raise ScenarioChannelError("unsupported materialization schema version")
    if materialization.get("plan_version") != PLAN_VERSION:
        raise ScenarioChannelError("materialization plan version mismatch")
    if materialization.get("protocol_version") != PROTOCOL_VERSION:
        raise ScenarioChannelError("materialization protocol version mismatch")
    _require_hex_field(
        materialization.get("source_cb01_lineage_sha256"),
        length=64,
        field="source_cb01_lineage_sha256",
    )
    _require_hex_field(
        materialization.get("study_repository_commit"),
        length=40,
        field="study_repository_commit",
    )

    raw_cases = materialization.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(case, Mapping) for case in raw_cases):
        raise ScenarioChannelError("materialization cases must contain only objects")
    if materialization.get("selected_case_count") != len(raw_cases):
        raise ScenarioChannelError("materialization selected_case_count mismatch")
    ids = [str(case.get("transition_id")) for case in raw_cases]
    if len(ids) != len(set(ids)):
        raise ScenarioChannelError("materialization contains duplicate transition IDs")
    return list(raw_cases)


def prepare_scenario_channels(
    materialization_path: Path,
    materialization_schema_path: Path,
) -> dict[str, Any]:
    """Create a bound worksheet without inventing or materializing scenario corpora."""

    materialization, materialization_bytes = _read_json_object_bytes(
        materialization_path, label="materialization"
    )
    cases = _validate_materialization(materialization, materialization_schema_path)
    return {
        "schema_version": SCENARIO_CHANNEL_SET_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "measurement_contract_version": MEASUREMENT_CONTRACT_VERSION,
        "source_materialization_sha256": _sha256_bytes(materialization_bytes),
        "generated_at": _utc_now(),
        "product_output_consulted": False,
        "case_count": len(cases),
        "cases": [
            {
                "rank": case["rank"],
                "transition_id": case["transition_id"],
                "status": "pending",
                "primary_channel_state": None,
                "absence_reason": None,
                "scenario_sets": [],
                "notes": None,
            }
            for case in cases
        ],
    }


def _resolve_artifact(root: Path, relative_path: str, *, case_id: str) -> Path:
    if "\\" in relative_path:
        raise ScenarioChannelError(
            f"scenario artifact for {case_id} must use POSIX separators: {relative_path!r}"
        )
    pure = PurePosixPath(relative_path)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise ScenarioChannelError(
            f"scenario artifact for {case_id} must stay below materialization root: "
            f"{relative_path!r}"
        )
    expected_prefix = PurePosixPath("cases") / case_id / "scenarios"
    if tuple(pure.parts[:3]) != tuple(expected_prefix.parts):
        raise ScenarioChannelError(
            f"scenario artifact for {case_id} must live below {expected_prefix.as_posix()}/"
        )

    candidate = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ScenarioChannelError(
                f"scenario artifact for {case_id} must not traverse a symlink: {relative_path!r}"
            )
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ScenarioChannelError(
            f"scenario artifact for {case_id} does not exist: {relative_path!r}"
        ) from exc
    if not resolved.is_relative_to(root):
        raise ScenarioChannelError(
            f"scenario artifact for {case_id} resolves outside materialization root"
        )
    if not resolved.is_file():
        raise ScenarioChannelError(f"scenario artifact for {case_id} is not a regular file")
    return resolved


def _validate_scenario_set(
    *, root: Path, case_id: str, scenario_set: Mapping[str, Any]
) -> tuple[bool, bool]:
    provenance = scenario_set.get("provenance")
    if provenance not in _VALID_PROVENANCE:
        raise ScenarioChannelError(f"invalid scenario provenance for {case_id}")

    expected_primary_admissible = provenance in _PRIMARY_ADMISSIBLE_PROVENANCE
    if scenario_set.get("primary_admissible") is not expected_primary_admissible:
        raise ScenarioChannelError(f"primary_admissible does not match provenance for {case_id}")

    if provenance == "PRODUCT_GENERATED":
        if scenario_set.get("generation_cost_accounting_required") is not True:
            raise ScenarioChannelError(
                f"PRODUCT_GENERATED scenario requires generation-cost accounting for {case_id}"
            )
        raise ScenarioChannelError(
            "PRODUCT_GENERATED scenario cannot exist in the pre-execution scenario registry "
            f"for {case_id}"
        )
    if scenario_set.get("generation_cost_accounting_required") is not False:
        raise ScenarioChannelError(
            "non-product-generated scenario must not claim generation-cost accounting "
            f"for {case_id}"
        )

    evidence_refs = scenario_set.get("provenance_evidence_refs")
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or not all(isinstance(item, str) and item.strip() for item in evidence_refs)
    ):
        raise ScenarioChannelError(f"scenario provenance evidence is required for {case_id}")

    artifact = scenario_set.get("artifact")
    if not isinstance(artifact, Mapping):
        raise ScenarioChannelError(f"scenario artifact metadata is required for {case_id}")
    relative_path = artifact.get("path")
    expected_sha256 = artifact.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_sha256, str):
        raise ScenarioChannelError(f"scenario artifact metadata is malformed for {case_id}")
    resolved = _resolve_artifact(root, relative_path, case_id=case_id)
    actual_sha256 = _sha256_file(resolved)
    if actual_sha256 != expected_sha256:
        raise ScenarioChannelError(
            f"scenario artifact SHA-256 mismatch for {case_id}: expected {expected_sha256}, "
            f"got {actual_sha256}"
        )
    return expected_primary_admissible, provenance in _DIAGNOSTIC_ONLY_PROVENANCE


def validate_scenario_channels(
    materialization_path: Path,
    scenario_channels_path: Path,
    *,
    materialization_schema_path: Path,
    scenario_schema_path: Path,
) -> dict[str, Any]:
    """Validate provenance, primary-channel availability, membership, and artifact digests."""

    materialization, materialization_bytes = _read_json_object_bytes(
        materialization_path, label="materialization"
    )
    materialization_cases = _validate_materialization(materialization, materialization_schema_path)

    scenario_channels, scenario_bytes = _read_json_object_bytes(
        scenario_channels_path, label="scenario channel set"
    )
    _validate_schema(scenario_channels, scenario_schema_path, label="scenario channel set")
    if scenario_channels.get("schema_version") != SCENARIO_CHANNEL_SET_SCHEMA_VERSION:
        raise ScenarioChannelError("unsupported scenario channel set schema version")
    if scenario_channels.get("plan_version") != PLAN_VERSION:
        raise ScenarioChannelError("scenario channel plan version mismatch")
    if scenario_channels.get("protocol_version") != PROTOCOL_VERSION:
        raise ScenarioChannelError("scenario channel protocol version mismatch")
    if scenario_channels.get("measurement_contract_version") != MEASUREMENT_CONTRACT_VERSION:
        raise ScenarioChannelError("scenario channel measurement contract version mismatch")
    if scenario_channels.get("product_output_consulted") is not False:
        raise ScenarioChannelError("scenario channel evidence is contaminated by product output")
    if scenario_channels.get("source_materialization_sha256") != _sha256_bytes(
        materialization_bytes
    ):
        raise ScenarioChannelError("scenario channel set is not bound to materialization")

    raw_cases = scenario_channels.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(case, Mapping) for case in raw_cases):
        raise ScenarioChannelError("scenario channel cases must contain only objects")
    scenario_cases = list(raw_cases)
    if scenario_channels.get("case_count") != len(scenario_cases):
        raise ScenarioChannelError("scenario channel case_count mismatch")

    materialization_ids = [str(case["transition_id"]) for case in materialization_cases]
    scenario_ids = [str(case.get("transition_id")) for case in scenario_cases]
    if scenario_ids != materialization_ids:
        raise ScenarioChannelError(
            "scenario channel membership/order does not match materialization"
        )

    root = materialization_path.resolve().parent
    primary_present_count = 0
    primary_absent_count = 0
    primary_set_count = 0
    diagnostic_set_count = 0

    for source_case, scenario_case in zip(materialization_cases, scenario_cases, strict=True):
        case_id = str(source_case["transition_id"])
        if scenario_case.get("rank") != source_case.get("rank"):
            raise ScenarioChannelError(f"scenario channel rank mismatch for {case_id}")
        if scenario_case.get("status") != "decided":
            raise ScenarioChannelError(f"scenario channel remains pending for {case_id}")

        raw_sets = scenario_case.get("scenario_sets")
        if not isinstance(raw_sets, list) or not all(
            isinstance(item, Mapping) for item in raw_sets
        ):
            raise ScenarioChannelError(f"scenario_sets must contain only objects for {case_id}")
        scenario_sets = list(raw_sets)
        set_ids = [str(item.get("id")) for item in scenario_sets]
        if len(set_ids) != len(set(set_ids)):
            raise ScenarioChannelError(f"duplicate scenario-set id for {case_id}")

        admissible_count = 0
        for scenario_set in scenario_sets:
            primary_admissible, diagnostic_only = _validate_scenario_set(
                root=root, case_id=case_id, scenario_set=scenario_set
            )
            if primary_admissible:
                admissible_count += 1
                primary_set_count += 1
            if diagnostic_only:
                diagnostic_set_count += 1

        state = scenario_case.get("primary_channel_state")
        absence_reason = scenario_case.get("absence_reason")
        if admissible_count:
            if state != "PRESENT":
                raise ScenarioChannelError(
                    f"primary channel must be PRESENT when admissible scenarios exist for {case_id}"
                )
            if absence_reason is not None:
                raise ScenarioChannelError(
                    f"present primary channel must not record absence_reason for {case_id}"
                )
            primary_present_count += 1
        else:
            if state != "ABSENT":
                raise ScenarioChannelError(
                    "primary channel must be ABSENT when no admissible scenarios exist "
                    f"for {case_id}"
                )
            if absence_reason != _ABSENCE_REASON:
                raise ScenarioChannelError(
                    f"absent primary channel requires {_ABSENCE_REASON} for {case_id}"
                )
            primary_absent_count += 1

    return {
        "schema_version": SCENARIO_CHANNEL_SET_SCHEMA_VERSION,
        "measurement_contract_version": MEASUREMENT_CONTRACT_VERSION,
        "source_materialization_sha256": _sha256_bytes(materialization_bytes),
        "scenario_channel_set_sha256": _sha256_bytes(scenario_bytes),
        "case_count": len(scenario_cases),
        "primary_present_count": primary_present_count,
        "primary_absent_count": primary_absent_count,
        "primary_scenario_set_count": primary_set_count,
        "diagnostic_scenario_set_count": diagnostic_set_count,
        "product_output_consulted": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="prepare scenario-channel worksheet")
    prepare.add_argument("--materialization", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument(
        "--materialization-schema",
        type=Path,
        default=root / "docs" / "r3-public-materialization-v2.schema.json",
    )

    validate = subparsers.add_parser("validate", help="validate frozen scenario channels")
    validate.add_argument("--materialization", type=Path, required=True)
    validate.add_argument("--scenario-channels", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    validate.add_argument(
        "--materialization-schema",
        type=Path,
        default=root / "docs" / "r3-public-materialization-v2.schema.json",
    )
    validate.add_argument(
        "--scenario-schema",
        type=Path,
        default=root / "docs" / "r3-scenario-channel-set.schema.json",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            worksheet = prepare_scenario_channels(args.materialization, args.materialization_schema)
            _validate_schema(
                worksheet,
                root / "docs" / "r3-scenario-channel-set.schema.json",
                label="scenario channel set",
            )
            _write_json(args.output, worksheet)
            return 0

        evidence = validate_scenario_channels(
            args.materialization,
            args.scenario_channels,
            materialization_schema_path=args.materialization_schema,
            scenario_schema_path=args.scenario_schema,
        )
        encoded = json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            if args.output.resolve() in {
                args.materialization.resolve(),
                args.scenario_channels.resolve(),
                args.materialization_schema.resolve(),
                args.scenario_schema.resolve(),
            }:
                raise ScenarioChannelError("validation output must not overwrite an input")
            _write_json(args.output, evidence)
    except ScenarioChannelError as exc:
        print(f"R3 scenario-channel validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
