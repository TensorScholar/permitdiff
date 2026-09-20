#!/usr/bin/env python3
"""Materialize exact public artifacts for the frozen R3 historical selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http.client import IncompleteRead, RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from scripts import r3_cb01_corpus_construction as _cb01
from scripts.discover_r3_benchmark_candidates import (
    PLAN_VERSION,
    PROTOCOL_VERSION,
    DiscoveryError,
    _resolve_token,
)
from scripts.discover_r3_public_benchmark_candidates import PublicOnlyGitHubClient

# Retained v1 identity for downstream CB-02+ readers (review packets, scenario
# channels, adjudications, locks), which still consume v1-shaped fixtures and
# import this constant. They migrate in their own packets; B5 must not break them.
MATERIALIZATION_SCHEMA_VERSION = "permitdiff.dev/r3-public-materialization/v1"
MATERIALIZATION_V2_SCHEMA_VERSION = "permitdiff.dev/r3-public-materialization/v2"
SELECTION_SCHEMA_VERSION = _cb01.SELECTION_SCHEMA_VERSION
LINEAGE_SCHEMA_VERSION = _cb01.LINEAGE_SCHEMA_VERSION
DEFAULT_CB01_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)


class MaterializationError(ValueError):
    """Raised when selected public artifacts cannot be reproduced exactly."""


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_object_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MaterializationError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MaterializationError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MaterializationError(f"{label} must contain a JSON object: {path}")
    return payload, raw


def _schema_error_path(error: ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _validate_against_schema(payload: dict[str, Any], schema_path: Path, *, label: str) -> None:
    schema, _ = _read_json_object_bytes(schema_path, label=f"{label} schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise MaterializationError(f"{label} schema is invalid: {exc.message}") from exc
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        None,
    )
    if error is not None:
        raise MaterializationError(
            f"{label} schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _load_contract_bytes(
    contract_path: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Load exact CB-01 contract bytes; hashing must use these exact bytes."""

    path = contract_path or DEFAULT_CB01_CONTRACT_PATH
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MaterializationError(f"failed to read CB-01 contract {path}: {exc}") from exc
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MaterializationError(f"CB-01 contract is not valid JSON: {path}: {exc}") from exc
    if not isinstance(contract, dict):
        raise MaterializationError(f"CB-01 contract must contain a JSON object: {path}")
    try:
        _cb01.validate_contract_binding(contract, raw)
    except _cb01.CB01ConstructionError as exc:
        raise MaterializationError(f"invalid CB-01 contract: {exc}") from exc
    return contract, raw


def _validate_selection(
    selection: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> list[Mapping[str, Any]]:
    """Validate selection v2 via the CB-01 single source of truth (no duplication)."""

    try:
        _cb01.validate_selection_v2(selection, contract, contract_bytes)
    except _cb01.CB01ConstructionError as exc:
        raise MaterializationError(str(exc)) from exc
    selected = selection.get("selected")
    assert isinstance(selected, list)
    return list(selected)


def _validate_lineage_gate(
    selection: Mapping[str, Any],
    selection_bytes: bytes,
    lineage: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> Mapping[str, Any]:
    """Gate fetching on selection v2 + lineage v1 consistency (before first fetch)."""

    if lineage.get("schema_version") != LINEAGE_SCHEMA_VERSION:
        raise MaterializationError("unsupported CB-01 construction lineage version")
    if lineage.get("cb01_contract_version") != _cb01.CB01_CONTRACT_VERSION:
        raise MaterializationError("lineage cb01 contract version mismatch")
    expected_contract_digest = _sha256_bytes(contract_bytes)
    if lineage.get("cb01_contract_sha256") != expected_contract_digest:
        raise MaterializationError("lineage contract digest does not match exact bytes")
    if lineage.get("public_selection_sha256") != _sha256_bytes(selection_bytes):
        raise MaterializationError("lineage is not bound to the supplied selection bytes")
    if lineage.get("study_repository_commit") != selection.get("study_repository_commit"):
        raise MaterializationError("lineage study commit does not match selection")
    for field in (
        "raw_eligible_count",
        "cap_admissible_count",
        "selected_case_count",
        "shortfall",
        "target_case_count",
        "maximum_cases_per_repository",
        "minimum_viable_case_count",
    ):
        if lineage.get(field) != selection.get(field):
            raise MaterializationError(
                f"lineage {field} does not match selection: "
                f"{lineage.get(field)!r} != {selection.get(field)!r}"
            )
    return lineage


def _exact_source_url(repository: str, commit: str, path: str) -> str:
    encoded_path = quote(path, safe="/")
    return f"https://github.com/{repository}/blob/{commit}/{encoded_path}"


def _validate_json_object(raw: bytes, *, transition_id: str, role: str) -> None:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterializationError(
            f"{transition_id} {role} artifact is no longer reproducible as valid JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise MaterializationError(f"{transition_id} {role} artifact is not a JSON object")


def _artifact_record(
    *,
    relative_path: str,
    expected_sha256: str,
    source_url: str,
    source_commit: str,
    source_blob: str,
    size_bytes: int,
) -> dict[str, Any]:
    return {
        "path": relative_path,
        "sha256": expected_sha256,
        "source_url": source_url,
        "source_commit": source_commit,
        "source_blob": source_blob,
        "size_bytes": size_bytes,
    }


def _fetch_role(
    client: PublicOnlyGitHubClient,
    *,
    case: Mapping[str, Any],
    role: str,
    staging_root: Path,
) -> dict[str, Any]:
    transition_id = str(case["transition_id"])
    repository = str(case["repository_full_name"])
    source_path = str(case["path"])
    commit = str(case[f"{role}_commit"])
    expected_blob = str(case[f"{role}_blob"])
    expected_sha256 = str(case[f"{role}_sha256"])

    metadata, raw = client.get_file(repository, source_path, commit)
    actual_blob = metadata.get("sha")
    if actual_blob != expected_blob:
        raise MaterializationError(
            f"{transition_id} {role} blob mismatch: expected {expected_blob}, got {actual_blob}"
        )
    actual_sha256 = _sha256_bytes(raw)
    if actual_sha256 != expected_sha256:
        raise MaterializationError(
            f"{transition_id} {role} SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    _validate_json_object(raw, transition_id=transition_id, role=role)

    relative_path = f"cases/{transition_id}/{role}.json"
    destination = staging_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return _artifact_record(
        relative_path=relative_path,
        expected_sha256=expected_sha256,
        source_url=_exact_source_url(repository, commit, source_path),
        source_commit=commit,
        source_blob=expected_blob,
        size_bytes=len(raw),
    )


def materialize_selection(
    selection_path: Path,
    lineage_path: Path,
    output_dir: Path,
    selection_schema_path: Path,
    lineage_schema_path: Path,
    materialization_schema_path: Path,
    contract_path: Path | None,
    client: PublicOnlyGitHubClient,
) -> dict[str, Any]:
    """Fetch and verify exact selected source bytes without executing PermitDiff.

    Packet B5: validates selection v2 + lineage v1 gates before the first
    source fetch. No fetch may occur unless all gates pass.
    """

    selection, selection_bytes = _read_json_object_bytes(selection_path, label="public selection")
    lineage, _lineage_bytes = _read_json_object_bytes(lineage_path, label="CB-01 lineage")
    contract, contract_bytes = _load_contract_bytes(contract_path)
    _validate_against_schema(selection, selection_schema_path, label="public selection")
    _validate_against_schema(lineage, lineage_schema_path, label="CB-01 lineage")
    selected = _validate_selection(selection, contract, contract_bytes)
    _validate_lineage_gate(selection, selection_bytes, lineage, contract, contract_bytes)

    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise MaterializationError(
            f"output directory already exists; refuse to overwrite evidence: {output_dir}"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent))
    visibility_cache: dict[str, dict[str, Any]] = {}
    materialized_cases: list[dict[str, Any]] = []
    try:
        for case in selected:
            repository = str(case["repository_full_name"])
            repository_metadata = visibility_cache.get(repository)
            if repository_metadata is None:
                repository_metadata = client.get_json(f"/repos/{repository}")
                visibility_cache[repository] = repository_metadata
            if repository_metadata.get("private") is not False:
                raise MaterializationError(
                    f"selected repository is not explicitly public at materialization: {repository}"
                )
            if repository_metadata.get("full_name") != repository:
                raise MaterializationError(
                    f"selected repository identity changed at materialization: {repository}"
                )

            baseline = _fetch_role(
                client,
                case=case,
                role="baseline",
                staging_root=staging,
            )
            candidate = _fetch_role(
                client,
                case=case,
                role="candidate",
                staging_root=staging,
            )
            materialized_cases.append(
                {
                    "rank": case["rank"],
                    "transition_id": case["transition_id"],
                    "repository_full_name": repository,
                    "repository_url": case["repository_url"],
                    "source_path": case["path"],
                    "selection_key": case["selection_key"],
                    "baseline": baseline,
                    "candidate": candidate,
                }
            )

        index = {
            "schema_version": MATERIALIZATION_V2_SCHEMA_VERSION,
            "plan_version": PLAN_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "source_selection_sha256": _sha256_bytes(selection_bytes),
            "source_cb01_lineage_sha256": _sha256_bytes(_lineage_bytes),
            "study_repository_commit": selection["study_repository_commit"],
            "generated_at": _utc_now(),
            "selected_case_count": len(materialized_cases),
            "cases": materialized_cases,
        }
        _validate_against_schema(index, materialization_schema_path, label="public materialization")
        (staging / "materialization.json").write_text(
            json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        staging.replace(output_dir)
        return index
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--selection-schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docs" / "r3-public-selection-v2.schema.json",
    )
    parser.add_argument(
        "--lineage-schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "docs"
        / "r3-cb01-corpus-construction-lineage.schema.json",
    )
    parser.add_argument(
        "--materialization-schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "docs"
        / "r3-public-materialization-v2.schema.json",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="CB-01 contract file; defaults to the committed contract",
    )
    args = parser.parse_args(argv)

    try:
        materialize_selection(
            args.selection,
            args.lineage,
            args.output_dir,
            args.selection_schema,
            args.lineage_schema,
            args.materialization_schema,
            args.contract,
            PublicOnlyGitHubClient(_resolve_token()),
        )
    except (DiscoveryError, IncompleteRead, MaterializationError, RemoteDisconnected) as exc:
        print(f"R3 public materialization failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
