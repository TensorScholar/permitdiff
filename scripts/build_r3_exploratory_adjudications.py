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
from scripts.materialize_r3_public_selection import MATERIALIZATION_SCHEMA_VERSION

ADJUDICATION_SCHEMA_VERSION = "permitdiff.dev/r3-adjudications/v1"
MANIFEST_SCHEMA_VERSION = "permitdiff.dev/r3-benchmark-case-manifest/v1"

_POSITIVE_LABEL = "SECURITY_RELEVANT_REGRESSION"
_VALID_LABELS = {
    _POSITIVE_LABEL,
    "BENIGN_OR_RESTRICTIVE_CHANGE",
    "UNKNOWN_OR_UNSUPPORTED",
}
_VALID_SUPPORT_BOUNDARIES = {"supported", "unsupported_or_unknown"}
_VALID_REVIEW_STATUSES = {"single_reviewed", "double_reviewed", "adjudicated"}


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
    if packet_set.get("product_output_prohibited") is not True:
        raise AdjudicationError("review packet set does not preserve product-output blinding")

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
    """Create an output-blind adjudication worksheet bound to exact review packets."""

    packet_set, packet_bytes = _read_json_object_bytes(
        review_packet_set_path, label="review packet set"
    )
    _validate_schema(packet_set, packet_schema_path, label="review packet set")
    cases = _validate_packet_set(packet_set)
    return {
        "schema_version": ADJUDICATION_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "source_review_packet_set_sha256": _sha256_bytes(packet_bytes),
        "generated_at": _utc_now(),
        "product_output_consulted": False,
        "cases": [
            {
                "rank": case["rank"],
                "transition_id": case["transition_id"],
                "status": "pending",
                "label": None,
                "support_boundary": None,
                "review_status": None,
                "reviewers": [],
                "rationale": None,
                "atomic_categories": [],
                "evidence_refs": [],
                "ambiguity_notes": None,
                "change_family": None,
            }
            for case in cases
        ],
    }


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

        label = decision.get("label")
        support_boundary = decision.get("support_boundary")
        review_status = decision.get("review_status")
        rationale = decision.get("rationale")
        reviewers = decision.get("reviewers")
        categories = decision.get("atomic_categories")
        evidence_refs = decision.get("evidence_refs")
        change_family = decision.get("change_family")

        if label not in _VALID_LABELS:
            raise AdjudicationError(f"invalid label for {transition_id}")
        if support_boundary not in _VALID_SUPPORT_BOUNDARIES:
            raise AdjudicationError(f"invalid support boundary for {transition_id}")
        if review_status not in _VALID_REVIEW_STATUSES:
            raise AdjudicationError(f"invalid review status for {transition_id}")
        if not isinstance(rationale, str) or not rationale.strip():
            raise AdjudicationError(f"missing rationale for {transition_id}")
        if not isinstance(reviewers, list) or not all(
            isinstance(item, str) and item.strip() for item in reviewers
        ):
            raise AdjudicationError(f"reviewers must be non-empty strings for {transition_id}")
        if review_status in {"double_reviewed", "adjudicated"} and len(set(reviewers)) < 2:
            raise AdjudicationError(
                f"{review_status} requires at least two distinct reviewers for {transition_id}"
            )
        if not isinstance(categories, list) or not all(
            isinstance(item, str) and item.strip() for item in categories
        ):
            raise AdjudicationError(f"atomic categories are malformed for {transition_id}")
        if label == _POSITIVE_LABEL and not categories:
            raise AdjudicationError(
                f"positive adjudication requires atomic categories for {transition_id}"
            )
        if not isinstance(evidence_refs, list) or not all(
            isinstance(item, str) and item.strip() for item in evidence_refs
        ):
            raise AdjudicationError(f"evidence refs are malformed for {transition_id}")
        if not evidence_refs:
            raise AdjudicationError(f"adjudication requires evidence refs for {transition_id}")
        if not isinstance(change_family, str) or not change_family.strip():
            raise AdjudicationError(f"change_family is required for {transition_id}")

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
    """Build the frozen public-historical manifest without running PermitDiff."""

    materialization, materialization_bytes = _read_json_object_bytes(
        materialization_path, label="public materialization"
    )
    _validate_schema(
        materialization, materialization_schema_path, label="public materialization"
    )
    if materialization.get("schema_version") != MATERIALIZATION_SCHEMA_VERSION:
        raise AdjudicationError("unsupported materialization schema version")
    if materialization.get("plan_version") != PLAN_VERSION:
        raise AdjudicationError("materialization plan version mismatch")
    if materialization.get("protocol_version") != PROTOCOL_VERSION:
        raise AdjudicationError("materialization protocol version mismatch")

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
    materialization_by_id = {
        str(case.get("transition_id")): case for case in materialization_cases
    }
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
                    f"Public historical Claude Code settings transition "
                    f"{source_case['repository_full_name']}:{source_case['source_path']}"
                ),
                "notes": _case_notes(decision),
                "tags": ["public-historical", "output-blind-adjudication"],
                "baseline": _manifest_artifact(source_case["baseline"]),
                "candidate": _manifest_artifact(source_case["candidate"]),
                "scenario_corpus": None,
                "adjudication": {
                    "label": decision["label"],
                    "support_boundary": decision["support_boundary"],
                    "review_status": decision["review_status"],
                    "rationale": decision["rationale"],
                    "atomic_categories": decision["atomic_categories"],
                    "reviewers": decision["reviewers"],
                    "evidence_refs": decision["evidence_refs"],
                },
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "corpus_id": corpus_id,
        "phase": "exploratory",
        "description": (
            "Output-blind R3 public historical exploratory slice; labels were recorded "
            "before PermitDiff execution."
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
        default=root / "docs" / "r3-public-materialization.schema.json",
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
        default=root / "docs" / "r3-benchmark-case-manifest.schema.json",
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
