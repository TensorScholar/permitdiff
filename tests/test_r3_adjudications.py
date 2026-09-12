from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_r3_exploratory_adjudications import (
    AdjudicationError,
    build_manifest,
    prepare_adjudications,
)

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZATION_SCHEMA = ROOT / "docs" / "r3-public-materialization.schema.json"
PACKET_SCHEMA = ROOT / "docs" / "r3-review-packet-set.schema.json"
ADJUDICATION_SCHEMA = ROOT / "docs" / "r3-adjudications.schema.json"
MANIFEST_SCHEMA = ROOT / "docs" / "r3-benchmark-case-manifest.schema.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixtures(root: Path) -> tuple[Path, Path]:
    transition_id = "gh-" + "1" * 20
    baseline = b'{"permissions":{"allow":["Read"]}}\n'
    candidate = b'{"permissions":{"allow":["Read","Bash(*)"]}}\n'
    cases = root / "cases" / transition_id
    cases.mkdir(parents=True)
    (cases / "baseline.json").write_bytes(baseline)
    (cases / "candidate.json").write_bytes(candidate)

    materialization = {
        "schema_version": "permitdiff.dev/r3-public-materialization/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_selection_sha256": "a" * 64,
        "generated_at": "2026-09-01T00:00:00Z",
        "selected_case_count": 1,
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_full_name": "public/example",
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "b" * 64,
                "baseline": {
                    "path": f"cases/{transition_id}/baseline.json",
                    "sha256": _sha256(baseline),
                    "source_url": (
                        "https://github.com/public/example/blob/"
                        + "c" * 40
                        + "/.claude/settings.json"
                    ),
                    "source_commit": "c" * 40,
                    "source_blob": "d" * 40,
                    "size_bytes": len(baseline),
                },
                "candidate": {
                    "path": f"cases/{transition_id}/candidate.json",
                    "sha256": _sha256(candidate),
                    "source_url": (
                        "https://github.com/public/example/blob/"
                        + "e" * 40
                        + "/.claude/settings.json"
                    ),
                    "source_commit": "e" * 40,
                    "source_blob": "f" * 40,
                    "size_bytes": len(candidate),
                },
            }
        ],
    }
    materialization_path = root / "materialization.json"
    _write_json(materialization_path, materialization)
    materialization_bytes = materialization_path.read_bytes()

    packet_set = {
        "schema_version": "permitdiff.dev/r3-review-packet-set/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_materialization_sha256": _sha256(materialization_bytes),
        "generated_at": "2026-09-01T00:00:01Z",
        "product_output_prohibited": True,
        "review_question": "Does this source transition regress authorization?",
        "label_definitions": {
            "SECURITY_RELEVANT_REGRESSION": "regression",
            "BENIGN_OR_RESTRICTIVE_CHANGE": "benign",
            "UNKNOWN_OR_UNSUPPORTED": "unknown",
        },
        "case_count": 1,
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "b" * 64,
                "documentation_refs": [
                    {
                        "url": "https://docs.example.test/permissions",
                        "title": "Permission semantics",
                        "version_or_date": "2026-09-01",
                        "notes": None,
                    }
                ],
                "context_notes": None,
                "baseline": materialization["cases"][0]["baseline"],
                "candidate": materialization["cases"][0]["candidate"],
                "source_diff": {
                    "path": f"cases/{transition_id}/source-diff.txt",
                    "sha256": "1" * 64,
                },
                "review_markdown": {
                    "path": f"cases/{transition_id}/review.md",
                    "sha256": "2" * 64,
                },
            }
        ],
    }
    packet_path = root / "review-packets.json"
    _write_json(packet_path, packet_set)
    return materialization_path, packet_path


def _decided(packet_path: Path, tmp_path: Path) -> Path:
    decisions = prepare_adjudications(packet_path, PACKET_SCHEMA)
    case = decisions["cases"][0]
    case.update(
        {
            "status": "decided",
            "label": "SECURITY_RELEVANT_REGRESSION",
            "support_boundary": "supported",
            "review_status": "single_reviewed",
            "reviewers": ["exploratory-reviewer-a"],
            "rationale": "Candidate adds documented preapproved Bash authority.",
            "atomic_categories": ["new_allow", "static_authority_expansion"],
            "evidence_refs": [
                "https://docs.example.test/permissions",
                f"review-packets/{case['transition_id']}/source-diff.txt",
            ],
            "ambiguity_notes": None,
            "change_family": "new_allow",
        }
    )
    path = tmp_path / "adjudications.json"
    _write_json(path, decisions)
    return path


def test_prepare_adjudications_is_bound_and_output_blind(tmp_path: Path) -> None:
    _, packet_path = _fixtures(tmp_path / "corpus")

    decisions = prepare_adjudications(packet_path, PACKET_SCHEMA)

    assert decisions["product_output_consulted"] is False
    assert decisions["cases"][0]["status"] == "pending"
    assert decisions["cases"][0]["label"] is None
    assert decisions["source_review_packet_set_sha256"] == _sha256(
        packet_path.read_bytes()
    )


def test_build_manifest_preserves_exact_public_artifact_provenance(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    output = corpus / "manifest.json"

    manifest = build_manifest(
        materialization_path,
        packet_path,
        adjudications_path,
        output,
        materialization_schema_path=MATERIALIZATION_SCHEMA,
        packet_schema_path=PACKET_SCHEMA,
        adjudication_schema_path=ADJUDICATION_SCHEMA,
        manifest_schema_path=MANIFEST_SCHEMA,
        corpus_id="r3-exploratory-public-historical-v1",
    )

    case = manifest["cases"][0]
    assert manifest["frozen_at"] is not None
    assert case["source_kind"] == "public_historical"
    assert case["adapter"] == "claude-code-project-preapprovals"
    assert case["baseline"]["source_commit"] == "c" * 40
    assert case["candidate"]["source_commit"] == "e" * 40
    assert case["adjudication"]["label"] == "SECURITY_RELEVANT_REGRESSION"
    assert output.exists()


def test_build_manifest_rejects_product_output_contamination(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    payload = json.loads(adjudications_path.read_text(encoding="utf-8"))
    payload["product_output_consulted"] = True
    _write_json(adjudications_path, payload)

    with pytest.raises(AdjudicationError, match="schema validation failed|contaminated"):
        build_manifest(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            manifest_schema_path=MANIFEST_SCHEMA,
            corpus_id="r3-exploratory-public-historical-v1",
        )


def test_build_manifest_rejects_positive_without_atomic_categories(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    payload = json.loads(adjudications_path.read_text(encoding="utf-8"))
    payload["cases"][0]["atomic_categories"] = []
    _write_json(adjudications_path, payload)

    with pytest.raises(AdjudicationError, match="schema validation failed|atomic categories"):
        build_manifest(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            manifest_schema_path=MANIFEST_SCHEMA,
            corpus_id="r3-exploratory-public-historical-v1",
        )


def test_build_manifest_rejects_double_review_claim_with_one_reviewer(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    payload = json.loads(adjudications_path.read_text(encoding="utf-8"))
    payload["cases"][0]["review_status"] = "double_reviewed"
    _write_json(adjudications_path, payload)

    with pytest.raises(AdjudicationError, match="requires at least two"):
        build_manifest(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            manifest_schema_path=MANIFEST_SCHEMA,
            corpus_id="r3-exploratory-public-historical-v1",
        )


def test_build_manifest_rejects_packet_set_bound_to_other_materialization(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["source_materialization_sha256"] = "0" * 64
    _write_json(packet_path, packet)

    with pytest.raises(AdjudicationError, match="not bound"):
        build_manifest(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            manifest_schema_path=MANIFEST_SCHEMA,
            corpus_id="r3-exploratory-public-historical-v1",
        )


def test_build_manifest_requires_canonical_artifact_relative_root(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)

    with pytest.raises(AdjudicationError, match="written beside materialization"):
        build_manifest(
            materialization_path,
            packet_path,
            adjudications_path,
            tmp_path / "elsewhere" / "manifest.json",
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            manifest_schema_path=MANIFEST_SCHEMA,
            corpus_id="r3-exploratory-public-historical-v1",
        )
