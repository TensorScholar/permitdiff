#!/usr/bin/env python3
"""Prepare output-blind R3 adjudications and build the exploratory public manifest."""

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
from scripts.build_r3_blinded_review_packets import REVIEW_PACKET_SET_SCHEMA_VERSION
from scripts.discover_r3_benchmark_candidates import PLAN_VERSION, PROTOCOL_VERSION
from scripts.materialize_r3_public_selection import MATERIALIZATION_V2_SCHEMA_VERSION


def _require_hex_field(value: Any, *, length: int, field: str) -> None:
    """Require a lowercase hex digest field (Packet C lineage/study binding)."""

    if (
        not isinstance(value, str)
        or len(value) != length
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise AdjudicationError(f"materialization has an invalid {field}")

ADJUDICATION_SCHEMA_VERSION = "permitdiff.dev/r3-adjudications/v2"
MANIFEST_SCHEMA_VERSION = "permitdiff.dev/r3-benchmark-case-manifest/v2"
MEASUREMENT_CONTRACT_VERSION = "r3-exploratory-measurement-contract-v2"

_VALID_SOURCE_RELATIONS = {
    "WIDENING",
    "RESTRICTIVE",
    "EQUIVALENT",
    "MIXED",
    "UNRESOLVED",
}
_VALID_TOOL_SUPPORT = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"}
_VALID_ORGANIZATIONAL_INTENT = {
    "KNOWN_INTENDED",
    "KNOWN_UNINTENDED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
}
_VALID_SOURCE_RESOLUTION = {"RESOLVED", "AMBIGUOUS", "UNAVAILABLE"}
_VALID_REVIEW_STATUSES = {"single_reviewed", "double_reviewed", "adjudicated"}
_VALID_CONTAMINATION_STATES = {
    "NO_KNOWN_PREEXPOSURE",
    "KNOWN_PREEXPOSURE",
    "UNKNOWN",
}


class AdjudicationError(ValueError):
    """Raised when output-blind adjudication evidence violates the R3 protocol contract."""


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_object_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AdjudicationError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdjudicationError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdjudicationError(f"{label} must contain a JSON object: {path}")
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
        raise AdjudicationError(f"{label} schema is invalid: {exc.message}") from exc
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        None,
    )
    if error is not None:
        raise AdjudicationError(
            f"{label} schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _validate_packet_set(packet_set: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if packet_set.get("schema_version") != REVIEW_PACKET_SET_SCHEMA_VERSION:
        raise AdjudicationError("unsupported review packet set schema version")
    if packet_set.get("plan_version") != PLAN_VERSION:
        raise AdjudicationError("review packet plan version mismatch")
    if packet_set.get("protocol_version") != PROTOCOL_VERSION:
        raise AdjudicationError("review packet protocol version mismatch")
    if packet_set.get("measurement_contract_version") != MEASUREMENT_CONTRACT_VERSION:
        raise AdjudicationError("review packet measurement contract version mismatch")
    if packet_set.get("product_output_prohibited") is not True:
        raise AdjudicationError("review packet set does not preserve product-output blinding")
    if packet_set.get("review_scope") != "source_semantics_only":
        raise AdjudicationError("review packet set does not preserve source-semantics-only scope")

    raw_cases = packet_set.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(case, Mapping) for case in raw_cases):
        raise AdjudicationError("review packet cases must contain only objects")
    if packet_set.get("case_count") != len(raw_cases):
        raise AdjudicationError("review packet case_count mismatch")

    ids = [str(case.get("transition_id")) for case in raw_cases]
    if len(ids) != len(set(ids)):
        raise AdjudicationError("review packet set contains duplicate transition IDs")
    return list(raw_cases)


def prepare_adjudications(
    review_packet_set_path: Path,
    packet_schema_path: Path,
) -> dict[str, Any]:
    """Create an output-blind multidimensional worksheet bound to exact review packets."""

    packet_set, packet_bytes = _read_json_object_bytes(
        review_packet_set_path, label="review packet set"
    )
    _validate_schema(packet_set, packet_schema_path, label="review packet set")
    cases = _validate_packet_set(packet_set)
    return {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "measurement_contract_version": MEASUREMENT_CONTRACT_VERSION,
        "source_review_packet_set_sha256": _sha256_bytes(packet_bytes),
        "generated_at": _utc_now(),
        "product_output_consulted": False,
        "cases": [
            {
                "rank": case["rank"],
                "transition_id": case["transition_id"],
                "status": "pending",
                "source_semantic_relation": None,
                "tool_support": None,
                "organizational_intent": None,
                "source_semantics_resolution": None,
                "review_status": None,
                "reviewers": [],
                "rationale": None,
                "atomic_categories": [],
                "evidence_refs": [],
                "ambiguity_notes": None,
                "change_family": None,
                "blinding_state": None,
                "contamination_state": None,
            }
            for case in cases
        ],
    }


def _require_nonempty_strings(value: object, *, field: str, transition_id: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise AdjudicationError(f"{field} must contain only non-empty strings for {transition_id}")
    return list(value)


def _validate_decisions(
    adjudications: Mapping[str, Any],
    packet_cases: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if adjudications.get("schema_version") != ADJUDICATION_SCHEMA_VERSION:
        raise AdjudicationError("unsupported adjudication schema version")
    if adjudications.get("plan_version") != PLAN_VERSION:
        raise AdjudicationError("adjudication plan version mismatch")
    if adjudications.get("protocol_version") != PROTOCOL_VERSION:
        raise AdjudicationError("adjudication protocol version mismatch")
    if adjudications.get("measurement_contract_version") != MEASUREMENT_CONTRACT_VERSION:
        raise AdjudicationError("adjudication measurement contract version mismatch")
    if adjudications.get("product_output_consulted") is not False:
        raise AdjudicationError("adjudications are contaminated by product output")

    raw_cases = adjudications.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(case, Mapping) for case in raw_cases):
        raise AdjudicationError("adjudication cases must contain only objects")
    decisions = list(raw_cases)
    packet_ids = [str(case["transition_id"]) for case in packet_cases]
    decision_ids = [str(case.get("transition_id")) for case in decisions]
    if decision_ids != packet_ids:
        raise AdjudicationError("adjudication membership/order does not match review packet set")

    for packet_case, decision in zip(packet_cases, decisions, strict=True):
        transition_id = str(packet_case["transition_id"])
        if decision.get("rank") != packet_case.get("rank"):
            raise AdjudicationError(f"adjudication rank mismatch for {transition_id}")
        if decision.get("status") != "decided":
            raise AdjudicationError(f"adjudication remains pending for {transition_id}")

        relation = decision.get("source_semantic_relation")
        tool_support = decision.get("tool_support")
        organizational_intent = decision.get("organizational_intent")
        resolution = decision.get("source_semantics_resolution")
        review_status = decision.get("review_status")
        rationale = decision.get("rationale")
        reviewers = decision.get("reviewers")
        categories = decision.get("atomic_categories")
        evidence_refs = decision.get("evidence_refs")
        ambiguity_notes = decision.get("ambiguity_notes")
        change_family = decision.get("change_family")
        blinding_state = decision.get("blinding_state")
        contamination_state = decision.get("contamination_state")

        if relation not in _VALID_SOURCE_RELATIONS:
            raise AdjudicationError(f"invalid source semantic relation for {transition_id}")
        if tool_support not in _VALID_TOOL_SUPPORT:
            raise AdjudicationError(f"invalid tool support for {transition_id}")
        if organizational_intent not in _VALID_ORGANIZATIONAL_INTENT:
            raise AdjudicationError(f"invalid organizational intent for {transition_id}")
        if resolution not in _VALID_SOURCE_RESOLUTION:
            raise AdjudicationError(f"invalid source semantics resolution for {transition_id}")
        if relation == "UNRESOLVED":
            if resolution not in {"AMBIGUOUS", "UNAVAILABLE"}:
                raise AdjudicationError(
                    f"UNRESOLVED requires AMBIGUOUS or UNAVAILABLE source semantics for "
                    f"{transition_id}"
                )
            if not isinstance(ambiguity_notes, str) or not ambiguity_notes.strip():
                raise AdjudicationError(f"UNRESOLVED requires ambiguity notes for {transition_id}")
        elif resolution != "RESOLVED":
            raise AdjudicationError(
                f"{relation} requires RESOLVED source semantics for {transition_id}"
            )

        if review_status not in _VALID_REVIEW_STATUSES:
            raise AdjudicationError(f"invalid review status for {transition_id}")
        if not isinstance(rationale, str) or not rationale.strip():
            raise AdjudicationError(f"missing rationale for {transition_id}")
        reviewer_values = _require_nonempty_strings(
            reviewers, field="reviewers", transition_id=transition_id
        )
        if review_status in {"double_reviewed", "adjudicated"} and len(set(reviewer_values)) < 2:
            raise AdjudicationError(
                f"{review_status} requires at least two distinct reviewers for {transition_id}"
            )

        _require_nonempty_strings(
            categories, field="atomic categories", transition_id=transition_id
        )
        evidence_values = _require_nonempty_strings(
            evidence_refs, field="evidence refs", transition_id=transition_id
        )
        if not evidence_values:
            raise AdjudicationError(f"adjudication requires evidence refs for {transition_id}")
        if not isinstance(change_family, str) or not change_family.strip():
            raise AdjudicationError(f"change_family is required for {transition_id}")
        if blinding_state != "OUTPUT_BLIND":
            raise AdjudicationError(f"adjudication is not output-blind for {transition_id}")
        if contamination_state not in _VALID_CONTAMINATION_STATES:
            raise AdjudicationError(f"invalid contamination state for {transition_id}")

    return decisions


def _manifest_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": artifact["path"],
        "sha256": artifact["sha256"],
        "source_url": artifact["source_url"],
        "source_commit": artifact["source_commit"],
        "source_blob": artifact["source_blob"],
    }


def _case_notes(decision: Mapping[str, Any]) -> str | None:
    ambiguity = decision.get("ambiguity_notes")
    if ambiguity is None:
        return None
    value = str(ambiguity).strip()
    return value or None


def build_manifest(
    materialization_path: Path,
    review_packet_set_path: Path,
    adjudications_path: Path,
    output_path: Path,
    *,
    materialization_schema_path: Path,
    packet_schema_path: Path,
    adjudication_schema_path: Path,
    manifest_schema_path: Path,
    corpus_id: str,
) -> dict[str, Any]:
    """Build the frozen public-historical v2 manifest without running PermitDiff."""

    materialization, materialization_bytes = _read_json_object_bytes(
        materialization_path, label="public materialization"
    )
    _validate_schema(materialization, materialization_schema_path, label="public materialization")
    if materialization.get("schema_version") != MATERIALIZATION_V2_SCHEMA_VERSION:
        raise AdjudicationError("unsupported materialization schema version")
    if materialization.get("plan_version") != PLAN_VERSION:
        raise AdjudicationError("materialization plan version mismatch")
    if materialization.get("protocol_version") != PROTOCOL_VERSION:
        raise AdjudicationError("materialization protocol version mismatch")
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

    packet_set, packet_bytes = _read_json_object_bytes(
        review_packet_set_path, label="review packet set"
    )
    _validate_schema(packet_set, packet_schema_path, label="review packet set")
    packet_cases = _validate_packet_set(packet_set)
    if packet_set.get("source_materialization_sha256") != _sha256_bytes(materialization_bytes):
        raise AdjudicationError("review packet set is not bound to the supplied materialization")

    adjudications, _ = _read_json_object_bytes(adjudications_path, label="adjudications")
    _validate_schema(adjudications, adjudication_schema_path, label="adjudications")
    if adjudications.get("source_review_packet_set_sha256") != _sha256_bytes(packet_bytes):
        raise AdjudicationError("adjudications are not bound to the supplied review packet set")
    decisions = _validate_decisions(adjudications, packet_cases)

    raw_materialization_cases = materialization.get("cases")
    if not isinstance(raw_materialization_cases, list) or not all(
        isinstance(case, Mapping) for case in raw_materialization_cases
    ):
        raise AdjudicationError("materialization cases must contain only objects")
    materialization_cases = list(raw_materialization_cases)
    materialization_by_id = {str(case.get("transition_id")): case for case in materialization_cases}
    if len(materialization_by_id) != len(materialization_cases):
        raise AdjudicationError("materialization contains duplicate transition IDs")

    packet_ids = [str(case["transition_id"]) for case in packet_cases]
    if set(materialization_by_id) != set(packet_ids):
        raise AdjudicationError("materialization membership does not match review packet set")

    expected_root = materialization_path.resolve().parent
    if output_path.resolve().parent != expected_root:
        raise AdjudicationError(
            "manifest must be written beside materialization.json so artifact paths stay canonical"
        )
    if output_path.exists():
        raise AdjudicationError(f"refuse to overwrite existing manifest: {output_path}")

    manifest_cases: list[dict[str, Any]] = []
    for packet_case, decision in zip(packet_cases, decisions, strict=True):
        transition_id = str(packet_case["transition_id"])
        source_case = materialization_by_id[transition_id]
        if source_case.get("rank") != packet_case.get("rank"):
            raise AdjudicationError(f"materialization rank mismatch for {transition_id}")
        if source_case.get("selection_key") != packet_case.get("selection_key"):
            raise AdjudicationError(f"selection key mismatch for {transition_id}")

        manifest_cases.append(
            {
                "id": transition_id,
                "source_kind": "public_historical",
                "source_system": "claude-code",
                "change_family": decision["change_family"],
                "adapter": "claude-code-project-preapprovals",
                "description": (
                    "Public historical Claude Code settings transition "
                    f"{source_case['repository_full_name']}:{source_case['source_path']}"
                ),
                "notes": _case_notes(decision),
                "tags": ["public-historical", "output-blind-adjudication"],
                "baseline": _manifest_artifact(source_case["baseline"]),
                "candidate": _manifest_artifact(source_case["candidate"]),
                "scenario_corpus": None,
                "adjudication": {
                    "source_semantic_relation": decision["source_semantic_relation"],
                    "tool_support": decision["tool_support"],
                    "organizational_intent": decision["organizational_intent"],
                    "source_semantics_resolution": decision["source_semantics_resolution"],
                    "review_status": decision["review_status"],
                    "rationale": decision["rationale"],
                    "atomic_categories": decision["atomic_categories"],
                    "reviewers": decision["reviewers"],
                    "evidence_refs": decision["evidence_refs"],
                    "ambiguity_notes": decision["ambiguity_notes"],
                    "blinding_state": decision["blinding_state"],
                    "contamination_state": decision["contamination_state"],
                },
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "measurement_contract_version": MEASUREMENT_CONTRACT_VERSION,
        "corpus_id": corpus_id,
        "phase": "exploratory",
        "description": (
            "Output-blind R3 public historical exploratory slice under the "
            "multidimensional measurement-contract-v2 adjudication model; "
            "source-semantic decisions were recorded before PermitDiff execution."
        ),
        "frozen_at": _utc_now(),
        "cases": manifest_cases,
    }
    _validate_schema(manifest, manifest_schema_path, label="benchmark manifest")
    _write_json(output_path, manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    root = Path(__file__).resolve().parents[1]

    prepare = subparsers.add_parser("prepare", help="prepare output-blind adjudications")
    prepare.add_argument("--review-packets", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument(
        "--packet-schema",
        type=Path,
        default=root / "docs" / "r3-review-packet-set.schema.json",
    )

    build = subparsers.add_parser("build-manifest", help="build frozen exploratory manifest")
    build.add_argument("--materialization", type=Path, required=True)
    build.add_argument("--review-packets", type=Path, required=True)
    build.add_argument("--adjudications", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--corpus-id", required=True)
    build.add_argument(
        "--materialization-schema",
        type=Path,
        default=root / "docs" / "r3-public-materialization-v2.schema.json",
    )
    build.add_argument(
        "--packet-schema",
        type=Path,
        default=root / "docs" / "r3-review-packet-set.schema.json",
    )
    build.add_argument(
        "--adjudication-schema",
        type=Path,
        default=root / "docs" / "r3-adjudications.schema.json",
    )
    build.add_argument(
        "--manifest-schema",
        type=Path,
        default=root / "docs" / "r3-benchmark-case-manifest-v2.schema.json",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            worksheet = prepare_adjudications(args.review_packets, args.packet_schema)
            _write_json(args.output, worksheet)
            return 0
        build_manifest(
            args.materialization,
            args.review_packets,
            args.adjudications,
            args.output,
            materialization_schema_path=args.materialization_schema,
            packet_schema_path=args.packet_schema,
            adjudication_schema_path=args.adjudication_schema,
            manifest_schema_path=args.manifest_schema,
            corpus_id=args.corpus_id,
        )
    except AdjudicationError as exc:
        print(f"R3 adjudication preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
