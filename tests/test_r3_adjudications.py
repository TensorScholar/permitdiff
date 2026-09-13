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
LEGACY_MANIFEST_SCHEMA = ROOT / "docs" / "r3-benchmark-case-manifest.schema.json"
MANIFEST_V2_SCHEMA = ROOT / "docs" / "r3-benchmark-case-manifest-v2.schema.json"


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
        "schema_version": "permitdiff.dev/r3-review-packet-set/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
        "source_materialization_sha256": _sha256(materialization_bytes),
        "generated_at": "2026-09-01T00:00:01Z",
        "product_output_prohibited": True,
        "review_scope": "source_semantics_only",
        "source_semantic_question": (
            "Under the frozen documented source semantics, what semantic relation holds?"
        ),
        "source_semantic_relation_definitions": {
            "WIDENING": "net authorization broadening",
            "RESTRICTIVE": "net authorization restriction",
            "EQUIVALENT": "semantically equivalent",
            "MIXED": "both widening and restrictive effects",
            "UNRESOLVED": "source relation cannot be established",
        },
        "source_semantics_resolution_definitions": {
            "RESOLVED": "source semantics sufficient",
            "AMBIGUOUS": "source semantics conflict or remain ambiguous",
            "UNAVAILABLE": "source semantics unavailable",
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


def _decided(
    packet_path: Path,
    tmp_path: Path,
    *,
    relation: str = "WIDENING",
    tool_support: str = "UNSUPPORTED",
    organizational_intent: str = "UNAVAILABLE",
    resolution: str = "RESOLVED",
    ambiguity_notes: str | None = None,
) -> Path:
    decisions = prepare_adjudications(packet_path, PACKET_SCHEMA)
    case = decisions["cases"][0]
    case.update(
        {
            "status": "decided",
            "source_semantic_relation": relation,
            "tool_support": tool_support,
            "organizational_intent": organizational_intent,
            "source_semantics_resolution": resolution,
            "review_status": "single_reviewed",
            "reviewers": ["exploratory-reviewer-a"],
            "rationale": "Frozen source semantics establish the recorded relation.",
            "atomic_categories": ["tool_or_scope_addition"] if relation == "WIDENING" else [],
            "evidence_refs": [
                "https://docs.example.test/permissions",
                f"review-packets/{case['transition_id']}/source-diff.txt",
            ],
            "ambiguity_notes": ambiguity_notes,
            "change_family": "tool_or_scope_change",
            "blinding_state": "OUTPUT_BLIND",
            "contamination_state": "NO_KNOWN_PREEXPOSURE",
        }
    )
    path = tmp_path / "adjudications.json"
    _write_json(path, decisions)
    return path


def _build(
    materialization_path: Path,
    packet_path: Path,
    adjudications_path: Path,
    output: Path,
) -> dict[str, object]:
    return build_manifest(
        materialization_path,
        packet_path,
        adjudications_path,
        output,
        materialization_schema_path=MATERIALIZATION_SCHEMA,
        packet_schema_path=PACKET_SCHEMA,
        adjudication_schema_path=ADJUDICATION_SCHEMA,
        manifest_schema_path=MANIFEST_V2_SCHEMA,
        corpus_id="r3-exploratory-public-historical-v1",
    )


def test_prepare_adjudications_is_bound_multidimensional_and_output_blind(tmp_path: Path) -> None:
    _, packet_path = _fixtures(tmp_path / "corpus")

    decisions = prepare_adjudications(packet_path, PACKET_SCHEMA)

    assert decisions["schema_version"] == "permitdiff.dev/r3-adjudications/v2"
    assert decisions["measurement_contract_version"] == "r3-exploratory-measurement-contract-v2"
    assert decisions["product_output_consulted"] is False
    case = decisions["cases"][0]
    assert case["status"] == "pending"
    assert case["source_semantic_relation"] is None
    assert case["tool_support"] is None
    assert case["organizational_intent"] is None
    assert case["source_semantics_resolution"] is None
    assert decisions["source_review_packet_set_sha256"] == _sha256(packet_path.read_bytes())
    serialized = json.dumps(decisions)
    assert "SECURITY_RELEVANT_REGRESSION" not in serialized
    assert "BENIGN_OR_RESTRICTIVE_CHANGE" not in serialized
    assert "UNKNOWN_OR_UNSUPPORTED" not in serialized


def test_build_manifest_preserves_widening_when_tool_is_unsupported(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(
        packet_path,
        tmp_path,
        relation="WIDENING",
        tool_support="UNSUPPORTED",
    )
    output = corpus / "manifest.json"

    manifest = _build(materialization_path, packet_path, adjudications_path, output)

    case = manifest["cases"][0]
    assert manifest["schema_version"] == "permitdiff.dev/r3-benchmark-case-manifest/v2"
    assert manifest["measurement_contract_version"] == "r3-exploratory-measurement-contract-v2"
    assert case["baseline"]["source_commit"] == "c" * 40
    assert case["candidate"]["source_commit"] == "e" * 40
    assert case["adjudication"]["source_semantic_relation"] == "WIDENING"
    assert case["adjudication"]["tool_support"] == "UNSUPPORTED"
    assert "label" not in case["adjudication"]
    assert "support_boundary" not in case["adjudication"]
    assert output.exists()


def test_unresolved_source_semantics_is_distinct_from_tool_support(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(
        packet_path,
        tmp_path,
        relation="UNRESOLVED",
        tool_support="SUPPORTED",
        resolution="AMBIGUOUS",
        ambiguity_notes="Public documentation does not resolve precedence.",
    )

    manifest = _build(
        materialization_path,
        packet_path,
        adjudications_path,
        corpus / "manifest.json",
    )

    adjudication = manifest["cases"][0]["adjudication"]
    assert adjudication["source_semantic_relation"] == "UNRESOLVED"
    assert adjudication["tool_support"] == "SUPPORTED"
    assert adjudication["source_semantics_resolution"] == "AMBIGUOUS"


def test_resolved_relation_rejects_nonresolved_source_semantics(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(
        packet_path,
        tmp_path,
        relation="WIDENING",
        resolution="AMBIGUOUS",
        ambiguity_notes="conflicting docs",
    )

    with pytest.raises(AdjudicationError, match=r"schema validation failed|requires RESOLVED"):
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
        )


def test_unresolved_relation_rejects_resolved_source_semantics(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(
        packet_path,
        tmp_path,
        relation="UNRESOLVED",
        resolution="RESOLVED",
        ambiguity_notes="cannot order relation",
    )

    with pytest.raises(
        AdjudicationError,
        match=r"schema validation failed|UNRESOLVED requires AMBIGUOUS or UNAVAILABLE",
    ):
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
        )


def test_decided_adjudication_requires_explicit_blinding_and_contamination_state(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    payload = json.loads(adjudications_path.read_text(encoding="utf-8"))
    payload["cases"][0]["blinding_state"] = None
    _write_json(adjudications_path, payload)

    with pytest.raises(AdjudicationError, match=r"schema validation failed|not output-blind"):
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
        )


def test_build_manifest_rejects_product_output_contamination(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    payload = json.loads(adjudications_path.read_text(encoding="utf-8"))
    payload["product_output_consulted"] = True
    _write_json(adjudications_path, payload)

    with pytest.raises(AdjudicationError, match=r"schema validation failed|contaminated"):
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
        )


def test_build_manifest_rejects_double_review_claim_with_one_reviewer(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)
    payload = json.loads(adjudications_path.read_text(encoding="utf-8"))
    payload["cases"][0]["review_status"] = "double_reviewed"
    _write_json(adjudications_path, payload)

    with pytest.raises(AdjudicationError, match="requires at least two"):
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
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
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            corpus / "manifest.json",
        )


def test_build_manifest_requires_canonical_artifact_relative_root(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    materialization_path, packet_path = _fixtures(corpus)
    adjudications_path = _decided(packet_path, tmp_path)

    with pytest.raises(AdjudicationError, match="written beside materialization"):
        _build(
            materialization_path,
            packet_path,
            adjudications_path,
            tmp_path / "elsewhere" / "manifest.json",
        )


def test_manifest_v1_contract_is_preserved_and_v2_is_explicitly_versioned() -> None:
    legacy = json.loads(LEGACY_MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    current = json.loads(MANIFEST_V2_SCHEMA.read_text(encoding="utf-8"))

    assert legacy["properties"]["schema_version"]["const"] == (
        "permitdiff.dev/r3-benchmark-case-manifest/v1"
    )
    assert current["properties"]["schema_version"]["const"] == (
        "permitdiff.dev/r3-benchmark-case-manifest/v2"
    )
    assert "label" in legacy["$defs"]["adjudication"]["properties"]
    assert "source_semantic_relation" in current["$defs"]["adjudication"]["properties"]
    assert "label" not in current["$defs"]["adjudication"]["properties"]
