#!/usr/bin/env python3
"""Validate R3 benchmark manifest structure, provenance metadata, and artifact digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

_VALIDATOR_VERSION = "permitdiff-r3-benchmark-integrity-v1"
_PUBLIC_SOURCE_KINDS = {"public_historical", "public_fixture"}
_ARTIFACT_ROLES = ("baseline", "candidate", "scenario_corpus")


class IntegrityError(ValueError):
    """Raised when benchmark evidence fails an integrity invariant."""


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IntegrityError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise IntegrityError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise IntegrityError(f"{label} must contain a JSON object: {path}")
    return payload


def _schema_error_path(error: ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _validate_schema(manifest: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise IntegrityError(f"benchmark manifest schema is invalid: {exc.message}") from exc

    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(validator.iter_errors(manifest), None)
    if error is not None:
        raise IntegrityError(
            f"manifest schema validation failed at {_schema_error_path(error)}: {error.message}"
        )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_artifact(root: Path, relative_path: str, *, case_id: str, role: str) -> Path:
    if "\\" in relative_path:
        raise IntegrityError(
            f"case {case_id!r} {role} path must use POSIX separators: {relative_path!r}"
        )

    pure_path = PurePosixPath(relative_path)
    if pure_path.is_absolute() or any(part == ".." for part in pure_path.parts):
        raise IntegrityError(
            f"case {case_id!r} {role} path must stay below the manifest directory: "
            f"{relative_path!r}"
        )

    candidate = root.joinpath(*pure_path.parts)
    cursor = root
    for part in pure_path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise IntegrityError(
                f"case {case_id!r} {role} artifact must not traverse a symlink: "
                f"{relative_path!r}"
            )

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise IntegrityError(
            f"case {case_id!r} {role} artifact does not exist: {relative_path!r}"
        ) from exc

    if not resolved.is_relative_to(root):
        raise IntegrityError(
            f"case {case_id!r} {role} artifact resolves outside the manifest directory: "
            f"{relative_path!r}"
        )
    if not resolved.is_file():
        raise IntegrityError(
            f"case {case_id!r} {role} artifact is not a regular file: {relative_path!r}"
        )
    return resolved


def _validate_source_metadata(
    *,
    case_id: str,
    source_kind: str,
    role: str,
    artifact: Mapping[str, Any],
) -> None:
    source_url = artifact.get("source_url")
    source_commit = artifact.get("source_commit")
    source_blob = artifact.get("source_blob")

    if (source_commit is not None or source_blob is not None) and source_url is None:
        raise IntegrityError(
            f"case {case_id!r} {role} has an immutable source identifier without source_url"
        )

    if source_url is not None:
        parsed = urlparse(str(source_url))
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise IntegrityError(
                f"case {case_id!r} {role} source_url must be an absolute HTTP(S) URL"
            )
        if parsed.username is not None or parsed.password is not None:
            raise IntegrityError(
                f"case {case_id!r} {role} source_url must not contain credentials"
            )

    if source_kind in _PUBLIC_SOURCE_KINDS and role in {"baseline", "candidate"}:
        if source_url is None or (source_commit is None and source_blob is None):
            raise IntegrityError(
                f"case {case_id!r} {role} public source requires source_url plus "
                "source_commit or source_blob"
            )


def _verify_artifact(
    *,
    root: Path,
    case_id: str,
    source_kind: str,
    role: str,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    relative_path = str(artifact["path"])
    expected_sha256 = str(artifact["sha256"])
    resolved = _resolve_artifact(root, relative_path, case_id=case_id, role=role)
    actual_sha256 = _sha256_file(resolved)
    if actual_sha256 != expected_sha256:
        raise IntegrityError(
            f"case {case_id!r} {role} SHA-256 mismatch for {relative_path!r}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    _validate_source_metadata(
        case_id=case_id,
        source_kind=source_kind,
        role=role,
        artifact=artifact,
    )
    return {
        "role": role,
        "path": relative_path,
        "sha256": actual_sha256,
        "size_bytes": resolved.stat().st_size,
        "source_url": artifact.get("source_url"),
        "source_commit": artifact.get("source_commit"),
        "source_blob": artifact.get("source_blob"),
    }


def validate_manifest(manifest_path: Path, schema_path: Path) -> dict[str, Any]:
    """Validate one manifest and return deterministic integrity evidence."""

    manifest_path = manifest_path.resolve()
    schema_path = schema_path.resolve()
    manifest = _read_json_object(manifest_path, label="benchmark manifest")
    schema = _read_json_object(schema_path, label="benchmark manifest schema")
    _validate_schema(manifest, schema)

    phase = str(manifest["phase"])
    if phase == "confirmatory" and manifest.get("frozen_at") is None:
        raise IntegrityError("confirmatory manifests require a non-null frozen_at timestamp")

    cases = manifest["cases"]
    if not isinstance(cases, list):
        raise IntegrityError("manifest cases must be a list")

    root = manifest_path.parent.resolve()
    seen_case_ids: set[str] = set()
    verified_cases: list[dict[str, Any]] = []
    artifact_count = 0

    for case in cases:
        if not isinstance(case, dict):
            raise IntegrityError("manifest case must be an object")
        case_id = str(case["id"])
        if case_id in seen_case_ids:
            raise IntegrityError(f"duplicate benchmark case id: {case_id!r}")
        seen_case_ids.add(case_id)

        source_kind = str(case["source_kind"])
        verified_artifacts: list[dict[str, Any]] = []
        for role in _ARTIFACT_ROLES:
            artifact = case.get(role)
            if artifact is None:
                continue
            if not isinstance(artifact, dict):
                raise IntegrityError(f"case {case_id!r} {role} must be an object")
            verified_artifacts.append(
                _verify_artifact(
                    root=root,
                    case_id=case_id,
                    source_kind=source_kind,
                    role=role,
                    artifact=artifact,
                )
            )
            artifact_count += 1

        verified_cases.append(
            {
                "id": case_id,
                "source_kind": source_kind,
                "source_system": case["source_system"],
                "artifacts": verified_artifacts,
            }
        )

    manifest_bytes = manifest_path.read_bytes()
    return {
        "validator_version": _VALIDATOR_VERSION,
        "schema_version": manifest["schema_version"],
        "protocol_version": manifest["protocol_version"],
        "corpus_id": manifest["corpus_id"],
        "phase": phase,
        "frozen_at": manifest.get("frozen_at"),
        "manifest_sha256": _sha256_bytes(manifest_bytes),
        "verified_case_count": len(verified_cases),
        "verified_artifact_count": artifact_count,
        "cases": verified_cases,
    }


def _protected_paths(manifest_path: Path, schema_path: Path, evidence: Mapping[str, Any]) -> set[Path]:
    root = manifest_path.parent.resolve()
    protected = {manifest_path.resolve(), schema_path.resolve()}
    cases = evidence.get("cases")
    if not isinstance(cases, list):
        return protected
    for case in cases:
        if not isinstance(case, dict):
            continue
        artifacts = case.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
                protected.add((root / artifact["path"]).resolve())
    return protected


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate R3 benchmark schema, provenance metadata, and SHA-256 digests."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "docs"
        / "r3-benchmark-case-manifest.schema.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        evidence = validate_manifest(args.manifest, args.schema)
        encoded = json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            output = args.output.resolve()
            if output in _protected_paths(args.manifest, args.schema, evidence):
                raise IntegrityError("output path must not overwrite the manifest, schema, or artifact")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8")
    except IntegrityError as exc:
        print(f"R3 benchmark integrity validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
