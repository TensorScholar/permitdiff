from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_r3_benchmark_manifest import IntegrityError, main, validate_manifest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs" / "r3-benchmark-case-manifest.schema.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_artifact(root: Path, relative: str, payload: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return _sha256(payload)


def _artifact(path: str, sha256: str) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": sha256,
        "source_blob": None,
        "source_commit": None,
        "source_url": None,
    }


def _manifest(root: Path) -> tuple[Path, dict[str, Any]]:
    baseline = _write_artifact(root, "cases/case-001/baseline.yaml", b"default: deny\n")
    candidate = _write_artifact(root, "cases/case-001/candidate.yaml", b"default: allow\n")
    corpus = _write_artifact(root, "cases/case-001/corpus.jsonl", b'{"id":"case-001"}\n')
    payload: dict[str, Any] = {
        "schema_version": "permitdiff.dev/r3-benchmark-case-manifest/v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "corpus_id": "test-exploratory-v1",
        "phase": "exploratory",
        "description": "test manifest",
        "frozen_at": None,
        "cases": [
            {
                "id": "case-001",
                "source_kind": "synthetic",
                "source_system": "permitdiff-policy",
                "change_family": "new_allow",
                "adapter": None,
                "description": "test case",
                "notes": None,
                "tags": ["test"],
                "baseline": _artifact("cases/case-001/baseline.yaml", baseline),
                "candidate": _artifact("cases/case-001/candidate.yaml", candidate),
                "scenario_corpus": _artifact("cases/case-001/corpus.jsonl", corpus),
                "adjudication": {
                    "label": "SECURITY_RELEVANT_REGRESSION",
                    "support_boundary": "supported",
                    "review_status": "single_reviewed",
                    "rationale": "candidate widens default authority",
                    "atomic_categories": ["new_allow"],
                    "reviewers": ["reviewer-a"],
                    "evidence_refs": ["README.md"],
                },
            }
        ],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path, payload


def _rewrite(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_valid_manifest_verifies_artifacts_and_emits_deterministic_evidence(tmp_path: Path) -> None:
    manifest_path, _ = _manifest(tmp_path)

    first = validate_manifest(manifest_path, SCHEMA)
    second = validate_manifest(manifest_path, SCHEMA)

    assert first == second
    assert first["validator_version"] == "permitdiff-r3-benchmark-integrity-v1"
    assert first["verified_case_count"] == 1
    assert first["verified_artifact_count"] == 3
    assert first["manifest_sha256"] == _sha256(manifest_path.read_bytes())
    assert [item["role"] for item in first["cases"][0]["artifacts"]] == [
        "baseline",
        "candidate",
        "scenario_corpus",
    ]


def test_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    payload["cases"][0]["candidate"]["sha256"] = "0" * 64
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="SHA-256 mismatch"):
        validate_manifest(manifest_path, SCHEMA)


def test_artifact_path_escape_is_rejected(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.yaml"
    outside.write_bytes(b"outside\n")
    payload["cases"][0]["baseline"]["path"] = f"../{outside.name}"
    payload["cases"][0]["baseline"]["sha256"] = _sha256(outside.read_bytes())
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="stay below the manifest directory"):
        validate_manifest(manifest_path, SCHEMA)


def test_duplicate_case_ids_are_rejected(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    payload["cases"].append(copy.deepcopy(payload["cases"][0]))
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="duplicate benchmark case id"):
        validate_manifest(manifest_path, SCHEMA)


def test_confirmatory_manifest_requires_frozen_timestamp(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    payload["phase"] = "confirmatory"
    payload["frozen_at"] = None
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="non-null frozen_at"):
        validate_manifest(manifest_path, SCHEMA)


def test_public_artifacts_require_immutable_source_provenance(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    payload["cases"][0]["source_kind"] = "public_historical"
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="public source requires source_url"):
        validate_manifest(manifest_path, SCHEMA)


def test_partial_provenance_without_source_url_is_rejected(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    payload["cases"][0]["baseline"]["source_commit"] = "a" * 40
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="without source_url"):
        validate_manifest(manifest_path, SCHEMA)


def test_schema_violation_is_rejected_before_integrity_checks(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    payload["cases"][0]["adjudication"]["label"] = "NOT_A_REAL_LABEL"
    _rewrite(manifest_path, payload)

    with pytest.raises(IntegrityError, match="schema validation failed"):
        validate_manifest(manifest_path, SCHEMA)


def test_cli_refuses_to_overwrite_verified_artifact(tmp_path: Path) -> None:
    manifest_path, payload = _manifest(tmp_path)
    baseline = tmp_path / payload["cases"][0]["baseline"]["path"]

    exit_code = main([str(manifest_path), "--schema", str(SCHEMA), "--output", str(baseline)])

    assert exit_code == 1
    assert baseline.read_bytes() == b"default: deny\n"
