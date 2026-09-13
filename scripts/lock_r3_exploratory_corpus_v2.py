#!/usr/bin/env python3
"""Create the complete R3 v2 pre-execution evidence lock without running PermitDiff."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from scripts.build_r3_exploratory_adjudications import MEASUREMENT_CONTRACT_VERSION
from scripts.build_r3_scenario_channels import validate_scenario_channels
from scripts.discover_r3_benchmark_candidates import PLAN_VERSION, PROTOCOL_VERSION
from scripts.lock_r3_exploratory_corpus import (
    PreExecutionLockError,
    create_pre_execution_lock as create_legacy_pre_execution_lock,
)

LOCK_SCHEMA_VERSION = "permitdiff.dev/r3-pre-execution-lock/v2"
MEASUREMENT_CONTRACT_SCHEMA_VERSION = "permitdiff.dev/r3-measurement-contract/v2"
SCENARIO_CHANNEL_INTEGRITY_VALIDATOR_VERSION = (
    "permitdiff-r3-scenario-channel-integrity-v1"
)

_FORBIDDEN_PRODUCT_OUTPUT_NAMES = {
    "permitdiff-result.json",
    "permitdiff-results.json",
    "benchmark-results.json",
    "r3-results.json",
}


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_object_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PreExecutionLockError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PreExecutionLockError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PreExecutionLockError(f"{label} must contain a JSON object: {path}")
    return payload, raw


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
        raise PreExecutionLockError(f"{label} schema is invalid: {exc.message}") from exc
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        None,
    )
    if error is not None:
        raise PreExecutionLockError(
            f"{label} schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _assert_bytes_unchanged(path: Path, expected: bytes, *, label: str) -> None:
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise PreExecutionLockError(f"failed to re-read {label} {path}: {exc}") from exc
    if current != expected:
        raise PreExecutionLockError(f"{label} changed during pre-execution lock validation")


def _common_evidence_root(paths: Sequence[Path]) -> Path:
    resolved = [path.resolve() for path in paths]
    common = resolved[0]
    while not all(path == common or path.is_relative_to(common) for path in resolved):
        if common.parent == common:
            raise PreExecutionLockError("failed to determine common pre-execution evidence root")
        common = common.parent
    return common if common.is_dir() else common.parent


def _assert_no_product_outputs(root: Path, output_dir: Path) -> None:
    output_resolved = output_dir.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved.is_relative_to(output_resolved):
            continue
        name = path.name.lower()
        if name in _FORBIDDEN_PRODUCT_OUTPUT_NAMES or name.startswith("permitdiff-results"):
            raise PreExecutionLockError(
                f"product execution artifact exists before pre-execution lock: {path}"
            )


def _validate_measurement_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != MEASUREMENT_CONTRACT_SCHEMA_VERSION:
        raise PreExecutionLockError("unsupported measurement contract schema version")
    if contract.get("measurement_contract_version") != MEASUREMENT_CONTRACT_VERSION:
        raise PreExecutionLockError("measurement contract version mismatch")
    if contract.get("parent_plan_version") != PLAN_VERSION:
        raise PreExecutionLockError("measurement contract parent plan version mismatch")
    if contract.get("protocol_version") != PROTOCOL_VERSION:
        raise PreExecutionLockError("measurement contract protocol version mismatch")
    if contract.get("adopted_before_canonical_labels") is not True:
        raise PreExecutionLockError("measurement contract was not adopted before canonical labels")
    if contract.get("adopted_before_product_execution") is not True:
        raise PreExecutionLockError("measurement contract was not adopted before product execution")


def create_complete_pre_execution_lock(
    *,
    manifest_path: Path,
    materialization_path: Path,
    review_packet_set_path: Path,
    adjudications_path: Path,
    measurement_contract_path: Path,
    scenario_channel_set_path: Path,
    output_dir: Path,
    manifest_schema_path: Path,
    materialization_schema_path: Path,
    packet_schema_path: Path,
    adjudication_schema_path: Path,
    measurement_contract_schema_path: Path,
    scenario_channel_schema_path: Path,
    legacy_lock_schema_path: Path,
    lock_schema_path: Path,
) -> dict[str, Any]:
    """Validate and digest-bind the complete R3 pre-execution evidence chain."""

    if output_dir.resolve().exists():
        raise PreExecutionLockError(
            f"output directory already exists; refuse to overwrite lock evidence: {output_dir}"
        )

    evidence_paths = [
        manifest_path,
        materialization_path,
        review_packet_set_path,
        adjudications_path,
        measurement_contract_path,
        scenario_channel_set_path,
    ]
    evidence_root = _common_evidence_root(evidence_paths)
    _assert_no_product_outputs(evidence_root, output_dir)

    snapshots: dict[str, tuple[Path, bytes]] = {}
    for label, path in (
        ("manifest", manifest_path),
        ("materialization", materialization_path),
        ("review packet set", review_packet_set_path),
        ("adjudications", adjudications_path),
        ("measurement contract", measurement_contract_path),
        ("scenario channel set", scenario_channel_set_path),
    ):
        _, raw = _read_json_object_bytes(path, label=label)
        snapshots[label] = (path, raw)

    measurement_contract, measurement_bytes = _read_json_object_bytes(
        measurement_contract_path, label="measurement contract"
    )
    _validate_schema(
        measurement_contract,
        measurement_contract_schema_path,
        label="measurement contract",
    )
    _validate_measurement_contract(measurement_contract)

    scenario_integrity = validate_scenario_channels(
        materialization_path,
        scenario_channel_set_path,
        materialization_schema_path=materialization_schema_path,
        scenario_schema_path=scenario_channel_schema_path,
    )
    _, scenario_bytes = _read_json_object_bytes(
        scenario_channel_set_path, label="scenario channel set"
    )
    if scenario_integrity.get("scenario_channel_set_sha256") != _sha256_bytes(scenario_bytes):
        raise PreExecutionLockError("scenario channel integrity digest mismatch")
    if scenario_integrity.get("measurement_contract_version") != MEASUREMENT_CONTRACT_VERSION:
        raise PreExecutionLockError("scenario channel measurement contract version mismatch")

    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix=".r3-lock-v2-work-", dir=output_dir.parent))
    legacy_output = work_root / "legacy-v1"
    staging = work_root / "final-v2"
    try:
        legacy_lock = create_legacy_pre_execution_lock(
            manifest_path=manifest_path,
            materialization_path=materialization_path,
            review_packet_set_path=review_packet_set_path,
            adjudications_path=adjudications_path,
            output_dir=legacy_output,
            manifest_schema_path=manifest_schema_path,
            materialization_schema_path=materialization_schema_path,
            packet_schema_path=packet_schema_path,
            adjudication_schema_path=adjudication_schema_path,
            lock_schema_path=legacy_lock_schema_path,
        )
        if legacy_lock.get("case_count") != scenario_integrity.get("case_count"):
            raise PreExecutionLockError("scenario channel integrity case_count mismatch")

        for label, (path, expected) in snapshots.items():
            _assert_bytes_unchanged(path, expected, label=label)

        staging.mkdir()
        manifest_integrity_source = legacy_output / "manifest-integrity.json"
        manifest_integrity_target = staging / "manifest-integrity.json"
        shutil.copyfile(manifest_integrity_source, manifest_integrity_target)
        manifest_integrity_bytes = manifest_integrity_target.read_bytes()

        scenario_integrity_evidence = {
            "validator_version": SCENARIO_CHANNEL_INTEGRITY_VALIDATOR_VERSION,
            **scenario_integrity,
        }
        scenario_integrity_path = staging / "scenario-channel-integrity.json"
        _write_json(scenario_integrity_path, scenario_integrity_evidence)
        scenario_integrity_bytes = scenario_integrity_path.read_bytes()

        lock = {
            "schema_version": LOCK_SCHEMA_VERSION,
            "plan_version": legacy_lock["plan_version"],
            "protocol_version": legacy_lock["protocol_version"],
            "measurement_contract_version": MEASUREMENT_CONTRACT_VERSION,
            "corpus_id": legacy_lock["corpus_id"],
            "locked_at": _utc_now(),
            "case_count": legacy_lock["case_count"],
            "product_execution_performed": False,
            "measurement_contract_sha256": _sha256_bytes(measurement_bytes),
            "manifest_sha256": legacy_lock["manifest_sha256"],
            "materialization_sha256": legacy_lock["materialization_sha256"],
            "review_packet_set_sha256": legacy_lock["review_packet_set_sha256"],
            "adjudications_sha256": legacy_lock["adjudications_sha256"],
            "scenario_channel_set_sha256": _sha256_bytes(scenario_bytes),
            "manifest_integrity_sha256": _sha256_bytes(manifest_integrity_bytes),
            "manifest_integrity_validator_version": legacy_lock[
                "manifest_integrity_validator_version"
            ],
            "scenario_channel_integrity_sha256": _sha256_bytes(scenario_integrity_bytes),
            "scenario_channel_integrity_validator_version": (
                SCENARIO_CHANNEL_INTEGRITY_VALIDATOR_VERSION
            ),
        }
        _validate_schema(lock, lock_schema_path, label="pre-execution lock v2")
        _write_json(staging / "pre-execution-lock.json", lock)
        staging.replace(output_dir)
        return lock
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--review-packets", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
    parser.add_argument(
        "--measurement-contract",
        type=Path,
        default=(
            root
            / "validation"
            / "r3-benchmark"
            / "exploratory"
            / "measurement-contract-v2.json"
        ),
    )
    parser.add_argument("--scenario-channels", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--manifest-schema",
        type=Path,
        default=root / "docs" / "r3-benchmark-case-manifest-v2.schema.json",
    )
    parser.add_argument(
        "--materialization-schema",
        type=Path,
        default=root / "docs" / "r3-public-materialization.schema.json",
    )
    parser.add_argument(
        "--packet-schema",
        type=Path,
        default=root / "docs" / "r3-review-packet-set.schema.json",
    )
    parser.add_argument(
        "--adjudication-schema",
        type=Path,
        default=root / "docs" / "r3-adjudications.schema.json",
    )
    parser.add_argument(
        "--measurement-contract-schema",
        type=Path,
        default=root / "docs" / "r3-measurement-contract.schema.json",
    )
    parser.add_argument(
        "--scenario-channel-schema",
        type=Path,
        default=root / "docs" / "r3-scenario-channel-set.schema.json",
    )
    parser.add_argument(
        "--legacy-lock-schema",
        type=Path,
        default=root / "docs" / "r3-pre-execution-lock.schema.json",
    )
    parser.add_argument(
        "--lock-schema",
        type=Path,
        default=root / "docs" / "r3-pre-execution-lock-v2.schema.json",
    )
    args = parser.parse_args(argv)

    try:
        create_complete_pre_execution_lock(
            manifest_path=args.manifest,
            materialization_path=args.materialization,
            review_packet_set_path=args.review_packets,
            adjudications_path=args.adjudications,
            measurement_contract_path=args.measurement_contract,
            scenario_channel_set_path=args.scenario_channels,
            output_dir=args.output_dir,
            manifest_schema_path=args.manifest_schema,
            materialization_schema_path=args.materialization_schema,
            packet_schema_path=args.packet_schema,
            adjudication_schema_path=args.adjudication_schema,
            measurement_contract_schema_path=args.measurement_contract_schema,
            scenario_channel_schema_path=args.scenario_channel_schema,
            legacy_lock_schema_path=args.legacy_lock_schema,
            lock_schema_path=args.lock_schema,
        )
    except (PreExecutionLockError, ValueError) as exc:
        print(f"R3 complete pre-execution lock failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
