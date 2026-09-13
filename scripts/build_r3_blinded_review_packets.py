#!/usr/bin/env python3
"""Prepare source-document context and build blinded R3 public review packets."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from scripts.discover_r3_benchmark_candidates import PLAN_VERSION, PROTOCOL_VERSION
from scripts.materialize_r3_public_selection import MATERIALIZATION_SCHEMA_VERSION

REVIEW_CONTEXT_SCHEMA_VERSION = "permitdiff.dev/r3-review-context/v1"
REVIEW_PACKET_SET_SCHEMA_VERSION = "permitdiff.dev/r3-review-packet-set/v2"
MEASUREMENT_CONTRACT_VERSION = "r3-exploratory-measurement-contract-v2"
_REVIEW_SCOPE = "source_semantics_only"
_SOURCE_SEMANTIC_QUESTION = (
    "Under the frozen documented source semantics and declared review assumptions, "
    "what semantic relation holds between the exact baseline and candidate artifacts?"
)
_SOURCE_SEMANTIC_RELATION_DEFINITIONS = {
    "WIDENING": (
        "Documented source semantics establish a net authorization broadening or "
        "approval-boundary weakening relevant to the frozen review scope."
    ),
    "RESTRICTIVE": "Documented source semantics establish a net restriction.",
    "EQUIVALENT": (
        "The changed authorization-relevant source state is semantically equivalent "
        "within the frozen review scope."
    ),
    "MIXED": (
        "Both widening and restrictive effects are established and a single directional "
        "ordering would be misleading."
    ),
    "UNRESOLVED": (
        "Available public source evidence cannot establish the source-level relation "
        "without undocumented runtime, precedence, or environment assumptions."
    ),
}
_SOURCE_SEMANTICS_RESOLUTION_DEFINITIONS = {
    "RESOLVED": (
        "The frozen source-system evidence is sufficient to resolve the relevant semantics "
        "under the declared review assumptions."
    ),
    "AMBIGUOUS": (
        "The frozen source-system evidence exists but leaves materially conflicting or "
        "ambiguous semantics."
    ),
    "UNAVAILABLE": (
        "Evidence required to resolve the relevant source-system semantics is unavailable "
        "within the frozen documentation set."
    ),
}


class ReviewPacketError(ValueError):
    """Raised when blinded review materials cannot preserve their evidence contract."""


def _utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json_object_bytes(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReviewPacketError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewPacketError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewPacketError(f"{label} must contain a JSON object: {path}")
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


def _validate_schema(payload: dict[str, Any], schema_path: Path, *, label: str) -> None:
    schema, _ = _read_json_object_bytes(schema_path, label=f"{label} schema")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ReviewPacketError(f"{label} schema is invalid: {exc.message}") from exc
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        None,
    )
    if error is not None:
        raise ReviewPacketError(
            f"{label} schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _validate_materialization(index: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if index.get("schema_version") != MATERIALIZATION_SCHEMA_VERSION:
        raise ReviewPacketError("unsupported public materialization schema version")
    if index.get("plan_version") != PLAN_VERSION:
        raise ReviewPacketError("materialization plan version mismatch")
    if index.get("protocol_version") != PROTOCOL_VERSION:
        raise ReviewPacketError("materialization protocol version mismatch")
    raw_cases = index.get("cases")
    if not isinstance(raw_cases, list) or not all(
        isinstance(case, Mapping) for case in raw_cases
    ):
        raise ReviewPacketError("materialization cases must contain only objects")
    if index.get("selected_case_count") != len(raw_cases):
        raise ReviewPacketError("materialization selected_case_count mismatch")
    ids = [str(case.get("transition_id")) for case in raw_cases]
    if len(ids) != len(set(ids)):
        raise ReviewPacketError("materialization contains duplicate transition IDs")
    return list(raw_cases)


def prepare_context(materialization_path: Path, materialization_schema: Path) -> dict[str, Any]:
    """Create a source-document context worksheet without any adjudication decisions."""

    index, index_bytes = _read_json_object_bytes(
        materialization_path, label="public materialization"
    )
    _validate_schema(index, materialization_schema, label="public materialization")
    cases = _validate_materialization(index)
    return {
        "schema_version": REVIEW_CONTEXT_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "source_materialization_sha256": _sha256_bytes(index_bytes),
        "generated_at": _utc_now(),
        "common_documentation_refs": [],
        "cases": [
            {
                "rank": case["rank"],
                "transition_id": case["transition_id"],
                "status": "pending",
                "documentation_refs": [],
                "notes": None,
            }
            for case in cases
        ],
    }


def _resolve_artifact(root: Path, relative_path: str, expected_sha256: str) -> bytes:
    pure = PurePosixPath(relative_path)
    if "\\" in relative_path or pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise ReviewPacketError(f"artifact path escapes materialization root: {relative_path}")
    path = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ReviewPacketError(f"artifact path traverses a symlink: {relative_path}")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ReviewPacketError(f"materialized artifact is missing: {relative_path}") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ReviewPacketError(f"invalid materialized artifact path: {relative_path}")
    raw = resolved.read_bytes()
    actual = _sha256_bytes(raw)
    if actual != expected_sha256:
        raise ReviewPacketError(
            f"materialized artifact digest mismatch for {relative_path}: "
            f"expected {expected_sha256}, got {actual}"
        )
    return raw


def _merge_documentation_refs(
    common: Sequence[Mapping[str, Any]],
    specific: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in [*common, *specific]:
        url = str(item["url"])
        if url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(dict(item))
    return merged


def _render_diff(baseline: bytes, candidate: bytes) -> bytes:
    baseline_lines = baseline.decode("utf-8").splitlines(keepends=True)
    candidate_lines = candidate.decode("utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(
        baseline_lines,
        candidate_lines,
        fromfile="baseline.json",
        tofile="candidate.json",
    )
    return "".join(diff).encode("utf-8")


def _markdown_packet(
    *,
    case: Mapping[str, Any],
    documentation_refs: Sequence[Mapping[str, Any]],
    notes: str | None,
) -> str:
    lines = [
        f"# R3 blinded review packet: {case['transition_id']}",
        "",
        "## Review boundary",
        "",
        "Do not consult PermitDiff output, normalized policies, findings, gates, or explanations.",
        "",
        "This packet is limited to source-system semantics. Do not determine PermitDiff "
        "tool support or organizational intent here; those are separate adjudication dimensions.",
        "",
        "The exploratory public-historical slice uses fixed-version semantic replay. "
        "Current frozen documentation defines the review semantics; this packet does not "
        "claim historical deployed runtime behavior.",
        "",
        f"**Source-semantic question:** {_SOURCE_SEMANTIC_QUESTION}",
        "",
        "Record exactly one `source_semantic_relation` during adjudication:",
        "",
    ]
    for relation, definition in _SOURCE_SEMANTIC_RELATION_DEFINITIONS.items():
        lines.append(f"- `{relation}` — {definition}")
    lines.extend(
        [
            "",
            "Record exactly one `source_semantics_resolution` during adjudication:",
            "",
        ]
    )
    for resolution, definition in _SOURCE_SEMANTICS_RESOLUTION_DEFINITIONS.items():
        lines.append(f"- `{resolution}` — {definition}")
    lines.extend(
        [
            "",
            "Consistency rule: any `source_semantic_relation` other than `UNRESOLVED` "
            "requires `source_semantics_resolution = RESOLVED`.",
            "",
            "`UNRESOLVED` is about source-semantic ground truth. It must not be used merely "
            "because PermitDiff does not support a construct.",
            "",
            "## Public source",
            "",
            f"- Repository: {case['repository_url']}",
            f"- Path: `{case['source_path']}`",
            f"- Baseline commit: `{case['baseline']['source_commit']}`",
            f"- Candidate commit: `{case['candidate']['source_commit']}`",
            "",
            "## Packet files",
            "",
            "- `baseline.json` — exact vendored baseline bytes",
            "- `candidate.json` — exact vendored candidate bytes",
            "- `source-diff.txt` — plain textual diff only",
            "",
            "## Source-system documentation",
            "",
        ]
    )
    for reference in documentation_refs:
        title = reference["title"]
        url = reference["url"]
        version = reference.get("version_or_date")
        suffix = "" if version is None else f" ({version})"
        lines.append(f"- {title}{suffix}: {url}")
    if notes is not None:
        lines.extend(["", "## Context notes", "", notes])
    lines.append("")
    return "\n".join(lines)


def _copy_artifact_record(
    artifact: Mapping[str, Any],
    *,
    new_path: str,
) -> dict[str, Any]:
    return {
        "path": new_path,
        "sha256": artifact["sha256"],
        "source_url": artifact["source_url"],
        "source_commit": artifact["source_commit"],
        "source_blob": artifact["source_blob"],
        "size_bytes": artifact["size_bytes"],
    }


def build_review_packets(
    materialization_path: Path,
    context_path: Path,
    output_dir: Path,
    materialization_schema: Path,
    context_schema: Path,
    packet_set_schema: Path,
) -> dict[str, Any]:
    """Build self-contained, output-blind packets from verified public source artifacts."""

    index, index_bytes = _read_json_object_bytes(
        materialization_path, label="public materialization"
    )
    _validate_schema(index, materialization_schema, label="public materialization")
    cases = _validate_materialization(index)
    context, _ = _read_json_object_bytes(context_path, label="review context")
    _validate_schema(context, context_schema, label="review context")

    if context.get("schema_version") != REVIEW_CONTEXT_SCHEMA_VERSION:
        raise ReviewPacketError("unsupported review context schema version")
    if context.get("plan_version") != PLAN_VERSION:
        raise ReviewPacketError("review context plan version mismatch")
    if context.get("protocol_version") != PROTOCOL_VERSION:
        raise ReviewPacketError("review context protocol version mismatch")
    if context.get("source_materialization_sha256") != _sha256_bytes(index_bytes):
        raise ReviewPacketError("review context is not bound to the supplied materialization")

    raw_context_cases = context.get("cases")
    if not isinstance(raw_context_cases, list):
        raise ReviewPacketError("review context cases must be a list")
    context_by_id: dict[str, Mapping[str, Any]] = {}
    for item in raw_context_cases:
        if not isinstance(item, Mapping):
            raise ReviewPacketError("review context contains a non-object case")
        transition_id = str(item.get("transition_id"))
        if transition_id in context_by_id:
            raise ReviewPacketError(f"duplicate review context for {transition_id}")
        context_by_id[transition_id] = item

    expected_ids = {str(case["transition_id"]) for case in cases}
    if set(context_by_id) != expected_ids:
        raise ReviewPacketError("review context membership does not match materialization")

    common_refs = context.get("common_documentation_refs")
    if not isinstance(common_refs, list):
        raise ReviewPacketError("common_documentation_refs must be a list")

    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ReviewPacketError(
            f"output directory already exists; refuse to overwrite packets: {output_dir}"
        )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    source_root = materialization_path.resolve().parent
    packet_cases: list[dict[str, Any]] = []
    try:
        for case in cases:
            transition_id = str(case["transition_id"])
            case_context = context_by_id[transition_id]
            if case_context.get("rank") != case.get("rank"):
                raise ReviewPacketError(f"review context rank mismatch for {transition_id}")
            if case_context.get("status") != "ready":
                raise ReviewPacketError(f"review context remains pending for {transition_id}")
            specific_refs = case_context.get("documentation_refs")
            if not isinstance(specific_refs, list):
                raise ReviewPacketError(
                    f"documentation_refs must be a list for {transition_id}"
                )
            documentation_refs = _merge_documentation_refs(common_refs, specific_refs)
            if not documentation_refs:
                raise ReviewPacketError(
                    f"no public source-system documentation supplied for {transition_id}"
                )

            baseline_record = case["baseline"]
            candidate_record = case["candidate"]
            baseline = _resolve_artifact(
                source_root,
                str(baseline_record["path"]),
                str(baseline_record["sha256"]),
            )
            candidate = _resolve_artifact(
                source_root,
                str(candidate_record["path"]),
                str(candidate_record["sha256"]),
            )

            case_root = staging / "cases" / transition_id
            case_root.mkdir(parents=True, exist_ok=True)
            (case_root / "baseline.json").write_bytes(baseline)
            (case_root / "candidate.json").write_bytes(candidate)
            diff_bytes = _render_diff(baseline, candidate)
            (case_root / "source-diff.txt").write_bytes(diff_bytes)

            notes = case_context.get("notes")
            markdown = _markdown_packet(
                case=case,
                documentation_refs=documentation_refs,
                notes=None if notes is None else str(notes),
            ).encode("utf-8")
            (case_root / "review.md").write_bytes(markdown)

            packet_cases.append(
                {
                    "rank": case["rank"],
                    "transition_id": transition_id,
                    "repository_url": case["repository_url"],
                    "source_path": case["source_path"],
                    "selection_key": case["selection_key"],
                    "documentation_refs": documentation_refs,
                    "context_notes": notes,
                    "baseline": _copy_artifact_record(
                        baseline_record,
                        new_path=f"cases/{transition_id}/baseline.json",
                    ),
                    "candidate": _copy_artifact_record(
                        candidate_record,
                        new_path=f"cases/{transition_id}/candidate.json",
                    ),
                    "source_diff": {
                        "path": f"cases/{transition_id}/source-diff.txt",
                        "sha256": _sha256_bytes(diff_bytes),
                    },
                    "review_markdown": {
                        "path": f"cases/{transition_id}/review.md",
                        "sha256": _sha256_bytes(markdown),
                    },
                }
            )

        packet_set = {
            "schema_version": REVIEW_PACKET_SET_SCHEMA_VERSION,
            "plan_version": PLAN_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "measurement_contract_version": MEASUREMENT_CONTRACT_VERSION,
            "source_materialization_sha256": _sha256_bytes(index_bytes),
            "generated_at": _utc_now(),
            "product_output_prohibited": True,
            "review_scope": _REVIEW_SCOPE,
            "source_semantic_question": _SOURCE_SEMANTIC_QUESTION,
            "source_semantic_relation_definitions": _SOURCE_SEMANTIC_RELATION_DEFINITIONS,
            "source_semantics_resolution_definitions": _SOURCE_SEMANTICS_RESOLUTION_DEFINITIONS,
            "case_count": len(packet_cases),
            "cases": packet_cases,
        }
        _validate_schema(packet_set, packet_set_schema, label="review packet set")
        _write_json(staging / "review-packets.json", packet_set)
        staging.replace(output_dir)
        return packet_set
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    root = Path(__file__).resolve().parents[1]

    prepare = subparsers.add_parser("prepare", help="prepare source-document context")
    prepare.add_argument("--materialization", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument(
        "--materialization-schema",
        type=Path,
        default=root / "docs" / "r3-public-materialization.schema.json",
    )

    build = subparsers.add_parser("build", help="build self-contained blinded packets")
    build.add_argument("--materialization", type=Path, required=True)
    build.add_argument("--context", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument(
        "--materialization-schema",
        type=Path,
        default=root / "docs" / "r3-public-materialization.schema.json",
    )
    build.add_argument(
        "--context-schema",
        type=Path,
        default=root / "docs" / "r3-review-context.schema.json",
    )
    build.add_argument(
        "--packet-set-schema",
        type=Path,
        default=root / "docs" / "r3-review-packet-set.schema.json",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            context = prepare_context(args.materialization, args.materialization_schema)
            _write_json(args.output, context)
            return 0
        build_review_packets(
            args.materialization,
            args.context,
            args.output_dir,
            args.materialization_schema,
            args.context_schema,
            args.packet_set_schema,
        )
    except ReviewPacketError as exc:
        print(f"R3 review packet preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
