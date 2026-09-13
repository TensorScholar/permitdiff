#!/usr/bin/env python3
"""Create the R3 exploratory pre-execution integrity lock without running PermitDiff."""

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

from scripts.build_r3_exploratory_adjudications import (
    ADJUDICATION_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MEASUREMENT_CONTRACT_VERSION,
)
from scripts.build_r3_blinded_review_packets import REVIEW_PACKET_SET_SCHEMA_VERSION
from scripts.discover_r3_benchmark_candidates import PLAN_VERSION, PROTOCOL_VERSION
from scripts.materialize_r3_public_selection import MATERIALIZATION_SCHEMA_VERSION
from scripts.validate_r3_benchmark_manifest import validate_manifest

LOCK_SCHEMA_VERSION = "permitdiff.dev/r3-pre-execution-lock/v1"

_FORBIDDEN_PRODUCT_OUTPUT_NAMES = {
    "permitdiff-result.json",
    "permitdiff-results.json",
    "benchmark-results.json",
    "r3-results.json",
}


class PreExecutionLockError(ValueError):
    """Raised when the exploratory corpus cannot be safely locked before execution."""


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


def _case_map(
    payload: Mapping[str, Any], *, id_field: str, label: str
) -> dict[str, Mapping[str, Any]]:
    raw = payload.get("cases")
    if not isinstance(raw, list) or not all(isinstance(case, Mapping) for case in raw):
        raise PreExecutionLockError(f"{label} cases must contain only objects")
    result: dict[str, Mapping[str, Any]] = {}
    for case in raw:
        case_id = str(case.get(id_field))
        if case_id in result:
            raise PreExecutionLockError(f"{label} contains duplicate case id {case_id}")
        result[case_id] = case
    return result


def _strip_materialized_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": artifact.get("path"),
        "sha256": artifact.get("sha256"),
        "source_url": artifact.get("source_url"),
        "source_commit": artifact.get("source_commit"),
        "source_blob": artifact.get("source_blob"),
    }


def _expected_manifest_adjudication(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_semantic_relation": decision.get("source_semantic_relation"),
        "tool_support": decision.get("tool_support"),
        "organizational_intent": decision.get("organizational_intent"),
        "source_semantics_resolution": decision.get("source_semantics_resolution"),
        "review_status": decision.get("review_status"),
        "rationale": decision.get("rationale"),
        "atomic_categories": decision.get("atomic_categories"),
        "reviewers": decision.get("reviewers"),
        "evidence_refs": decision.get("evidence_refs"),
        "ambiguity_notes": decision.get("ambiguity_notes"),
        "blinding_state": decision.get("blinding_state"),
        "contamination_state": decision.get("contamination_state"),
    }


def _assert_no_product_outputs(root: Path, output_dir: Path) -> None:
    output_dir_resolved = output_dir.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved.is_relative_to(output_dir_resolved):
            continue
        name = path.name.lower()
        if name in _FORBIDDEN_PRODUCT_OUTPUT_NAMES or name.startswith("permitdiff-results"):
            raise PreExecutionLockError(
                f"product execution artifact exists before pre-execution lock: {path}"
            )


def _validate_linkage(
    *,
    manifest: Mapping[str, Any],
    materialization: Mapping[str, Any],
    packet_set: Mapping[str, Any],
    adjudications: Mapping[str, Any],
    materialization_bytes: bytes,
    packet_bytes: bytes,
) -> int:
    if materialization.get("schema_version") != MATERIALIZATION_SCHEMA_VERSION:
        raise PreExecutionLockError("unsupported materialization schema version")
    if packet_set.get("schema_version") != REVIEW_PACKET_SET_SCHEMA_VERSION:
        raise PreExecutionLockError("unsupported review packet set schema version")
    if adjudications.get("schema_version") != ADJUDICATION_SCHEMA_VERSION:
        raise PreExecutionLockError("unsupported adjudication schema version")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise PreExecutionLockError("unsupported benchmark manifest schema version")

    for label, payload in (
        ("materialization", materialization),
        ("review packet set", packet_set),
        ("adjudications", adjudications),
    ):
        if payload.get("plan_version") != PLAN_VERSION:
            raise PreExecutionLockError(f"{label} plan version mismatch")
        if payload.get("protocol_version") != PROTOCOL_VERSION:
            raise PreExecutionLockError(f"{label} protocol version mismatch")

    if manifest.get("protocol_version") != PROTOCOL_VERSION:
        raise PreExecutionLockError("manifest protocol version mismatch")
    for label, payload in (
        ("review packet set", packet_set),
        ("adjudications", adjudications),
        ("manifest", manifest),
    ):
        if payload.get("measurement_contract_version") != MEASUREMENT_CONTRACT_VERSION:
            raise PreExecutionLockError(f"{label} measurement contract version mismatch")

    if packet_set.get("product_output_prohibited") is not True:
        raise PreExecutionLockError("review packet set does not enforce product-output blinding")
    if adjudications.get("product_output_consulted") is not False:
        raise PreExecutionLockError("adjudications record product-output contamination")
    if packet_set.get("source_materialization_sha256") != _sha256_bytes(materialization_bytes):
        raise PreExecutionLockError("review packet set/materialization digest linkage failed")
    if adjudications.get("source_review_packet_set_sha256") != _sha256_bytes(packet_bytes):
        raise PreExecutionLockError("adjudication/review-packet digest linkage failed")

    if manifest.get("phase") != "exploratory":
        raise PreExecutionLockError(
            "pre-execution lock currently supports exploratory manifests only"
        )
    if manifest.get("frozen_at") is None:
        raise PreExecutionLockError("exploratory manifest must be frozen before lock")

    manifest_cases = _case_map(manifest, id_field="id", label="manifest")
    materialized_cases = _case_map(
        materialization, id_field="transition_id", label="materialization"
    )
    packet_cases = _case_map(packet_set, id_field="transition_id", label="review packet set")
    decision_cases = _case_map(
        adjudications, id_field="transition_id", label="adjudications"
    )
    membership = set(manifest_cases)
    if membership != set(materialized_cases) or membership != set(packet_cases):
        raise PreExecutionLockError("manifest/materialization/review-packet membership mismatch")
    if membership != set(decision_cases):
        raise PreExecutionLockError("manifest/adjudication membership mismatch")

    for case_id in sorted(membership):
        manifest_case = manifest_cases[case_id]
        materialized = materialized_cases[case_id]
        packet_case = packet_cases[case_id]
        decision = decision_cases[case_id]

        if decision.get("status") != "decided":
            raise PreExecutionLockError(f"adjudication remains pending for {case_id}")
        if materialized.get("selection_key") != packet_case.get("selection_key"):
            raise PreExecutionLockError(f"selection key mismatch for {case_id}")
        if manifest_case.get("source_kind") != "public_historical":
            raise PreExecutionLockError(f"unexpected source_kind for {case_id}")

        if manifest_case.get("baseline") != _strip_materialized_artifact(
            materialized["baseline"]
        ):
            raise PreExecutionLockError(f"manifest baseline provenance mismatch for {case_id}")
        if manifest_case.get("candidate") != _strip_materialized_artifact(
            materialized["candidate"]
        ):
            raise PreExecutionLockError(f"manifest candidate provenance mismatch for {case_id}")
        if manifest_case.get("adjudication") != _expected_manifest_adjudication(decision):
            raise PreExecutionLockError(f"manifest adjudication mismatch for {case_id}")

    return len(membership)


def create_pre_execution_lock(
    *,
    manifest_path: Path,
    materialization_path: Path,
    review_packet_set_path: Path,
    adjudications_path: Path,
    output_dir: Path,
    manifest_schema_path: Path,
    materialization_schema_path: Path,
    packet_schema_path: Path,
    adjudication_schema_path: Path,
    lock_schema_path: Path,
) -> dict[str, Any]:
    """Validate the output-blind evidence chain and publish the current lock atomically."""

    manifest, manifest_bytes = _read_json_object_bytes(manifest_path, label="manifest")
    materialization, materialization_bytes = _read_json_object_bytes(
        materialization_path, label="materialization"
    )
    packet_set, packet_bytes = _read_json_object_bytes(
        review_packet_set_path, label="review packet set"
    )
    adjudications, adjudication_bytes = _read_json_object_bytes(
        adjudications_path, label="adjudications"
    )

    _validate_schema(manifest, manifest_schema_path, label="manifest")
    _validate_schema(
        materialization, materialization_schema_path, label="materialization"
    )
    _validate_schema(packet_set, packet_schema_path, label="review packet set")
    _validate_schema(adjudications, adjudication_schema_path, label="adjudications")

    case_count = _validate_linkage(
        manifest=manifest,
        materialization=materialization,
        packet_set=packet_set,
        adjudications=adjudications,
        materialization_bytes=materialization_bytes,
        packet_bytes=packet_bytes,
    )
    integrity = validate_manifest(manifest_path, manifest_schema_path)

    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise PreExecutionLockError(
            f"output directory already exists; refuse to overwrite lock evidence: {output_dir}"
        )
    root = manifest_path.resolve().parent
    _assert_no_product_outputs(root, output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        integrity_path = staging / "manifest-integrity.json"
        _write_json(integrity_path, integrity)
        integrity_bytes = integrity_path.read_bytes()
        lock = {
            "schema_version": LOCK_SCHEMA_VERSION,
            "plan_version": PLAN_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "corpus_id": manifest["corpus_id"],
            "locked_at": _utc_now(),
            "case_count": case_count,
            "product_execution_performed": False,
            "manifest_sha256": _sha256_bytes(manifest_bytes),
            "materialization_sha256": _sha256_bytes(materialization_bytes),
            "review_packet_set_sha256": _sha256_bytes(packet_bytes),
            "adjudications_sha256": _sha256_bytes(adjudication_bytes),
            "manifest_integrity_sha256": _sha256_bytes(integrity_bytes),
            "manifest_integrity_validator_version": integrity["validator_version"],
        }
        _validate_schema(lock, lock_schema_path, label="pre-execution lock")
        _write_json(staging / "pre-execution-lock.json", lock)
        staging.replace(output_dir)
        return lock
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--review-packets", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
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
        "--lock-schema",
        type=Path,
        default=root / "docs" / "r3-pre-execution-lock.schema.json",
    )
    args = parser.parse_args(argv)

    try:
        create_pre_execution_lock(
            manifest_path=args.manifest,
            materialization_path=args.materialization,
            review_packet_set_path=args.review_packets,
            adjudications_path=args.adjudications,
            output_dir=args.output_dir,
            manifest_schema_path=args.manifest_schema,
            materialization_schema_path=args.materialization_schema,
            packet_schema_path=args.packet_schema,
            adjudication_schema_path=args.adjudication_schema,
            lock_schema_path=args.lock_schema,
        )
    except (PreExecutionLockError, ValueError) as exc:
        print(f"R3 pre-execution lock failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
