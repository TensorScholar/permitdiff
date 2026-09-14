#!/usr/bin/env python3
"""Validate immutable R3 source-documentation snapshots and per-case evidence identity."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class DocumentationSnapshotError(ValueError):
    """Raised when frozen documentation evidence is mutable or inconsistent."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def documentation_set_digest(documents: list[dict[str, Any]]) -> str:
    identities = [
        {
            "document_id": doc["document_id"],
            "snapshot_sha256": doc["snapshot_sha256"],
        }
        for doc in documents
    ]
    canonical = json.dumps(identities, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(canonical)


def _resolve(root: Path, relative: str) -> Path:
    if "\\" in relative:
        raise DocumentationSnapshotError("snapshot paths must use POSIX separators")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise DocumentationSnapshotError(f"snapshot path escapes manifest root: {relative}")
    candidate = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise DocumentationSnapshotError(f"snapshot path traverses symlink: {relative}")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise DocumentationSnapshotError(f"snapshot file is missing: {relative}") from exc
    if not resolved.is_file() or not resolved.is_relative_to(root.resolve()):
        raise DocumentationSnapshotError(f"invalid snapshot path: {relative}")
    return resolved


def validate_manifest(
    manifest_path: Path,
    *,
    schema_path: Path = Path("docs/r3-documentation-snapshot-manifest.schema.json"),
    expected_case_ids: list[str] | None = None,
) -> dict[str, Any]:
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise DocumentationSnapshotError("documentation manifest must be a JSON object")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)

    root = manifest_path.resolve().parent
    raw_docs = manifest["documents"]
    if not isinstance(raw_docs, list):
        raise DocumentationSnapshotError("documents must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for doc in raw_docs:
        assert isinstance(doc, dict)
        doc_id = str(doc["document_id"])
        if doc_id in by_id:
            raise DocumentationSnapshotError(f"duplicate document_id: {doc_id}")
        path = _resolve(root, str(doc["snapshot_path"]))
        actual = _sha256(path.read_bytes())
        if actual != doc["snapshot_sha256"]:
            raise DocumentationSnapshotError(
                f"documentation snapshot hash mismatch for {doc_id}: {actual}"
            )
        by_id[doc_id] = doc

    raw_cases = manifest["cases"]
    assert isinstance(raw_cases, list)
    case_ids: list[str] = []
    for case in raw_cases:
        assert isinstance(case, dict)
        case_id = str(case["case_id"])
        if case_id in case_ids:
            raise DocumentationSnapshotError(f"duplicate case_id: {case_id}")
        case_ids.append(case_id)
        ids = list(case["documentation_ids"])
        missing = sorted(set(ids) - set(by_id))
        if missing:
            raise DocumentationSnapshotError(
                f"case {case_id} references unknown documents: {missing}"
            )
        selected = [by_id[doc_id] for doc_id in ids]
        expected = documentation_set_digest(selected)
        if case["documentation_snapshot_set_sha256"] != expected:
            raise DocumentationSnapshotError(f"documentation set digest mismatch for {case_id}")
    if expected_case_ids is not None and case_ids != expected_case_ids:
        raise DocumentationSnapshotError(
            "documentation case membership/order does not match lock population"
        )

    return {
        "manifest_sha256": _sha256(raw),
        "case_ids": case_ids,
        "document_count": len(by_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("docs/r3-documentation-snapshot-manifest.schema.json"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            validate_manifest(args.manifest, schema_path=args.schema),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
