from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_r3_blinded_review_packets import (
    ReviewPacketError,
    build_review_packets,
    prepare_context,
)

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZATION_SCHEMA = ROOT / "docs" / "r3-public-materialization.schema.json"
CONTEXT_SCHEMA = ROOT / "docs" / "r3-review-context.schema.json"
PACKET_SET_SCHEMA = ROOT / "docs" / "r3-review-packet-set.schema.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _materialization(root: Path) -> Path:
    transition_id = "gh-" + "1" * 20
    baseline = b'{\n  "permissions": {"allow": ["Read"]}\n}\n'
    candidate = b'{\n  "permissions": {"allow": ["Read", "Bash(*)"]}\n}\n'
    case_root = root / "cases" / transition_id
    case_root.mkdir(parents=True)
    (case_root / "baseline.json").write_bytes(baseline)
    (case_root / "candidate.json").write_bytes(candidate)
    index = {
        "schema_version": "permitdiff.dev/r3-public-materialization/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_selection_sha256": "9" * 64,
        "generated_at": "2026-09-01T00:00:00Z",
        "selected_case_count": 1,
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_full_name": "public/example",
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "8" * 64,
                "baseline": {
                    "path": f"cases/{transition_id}/baseline.json",
                    "sha256": _sha256(baseline),
                    "source_url": (
                        "https://github.com/public/example/blob/"
                        + "a" * 40
                        + "/.claude/settings.json"
                    ),
                    "source_commit": "a" * 40,
                    "source_blob": "c" * 40,
                    "size_bytes": len(baseline),
                },
                "candidate": {
                    "path": f"cases/{transition_id}/candidate.json",
                    "sha256": _sha256(candidate),
                    "source_url": (
                        "https://github.com/public/example/blob/"
                        + "b" * 40
                        + "/.claude/settings.json"
                    ),
                    "source_commit": "b" * 40,
                    "source_blob": "d" * 40,
                    "size_bytes": len(candidate),
                },
            }
        ],
    }
    path = root / "materialization.json"
    _write_json(path, index)
    return path


def _ready_context(materialization_path: Path, tmp_path: Path) -> Path:
    context = prepare_context(materialization_path, MATERIALIZATION_SCHEMA)
    context["common_documentation_refs"] = [
        {
            "url": "https://docs.example.test/permissions",
            "title": "Public permission semantics",
            "version_or_date": "2026-09-01",
            "notes": None,
        }
    ]
    context["cases"][0]["status"] = "ready"
    path = tmp_path / "review-context.json"
    _write_json(path, context)
    return path


def test_prepare_context_is_bound_and_contains_no_adjudication_decisions(tmp_path) -> None:
    materialization_path = _materialization(tmp_path / "source")

    context = prepare_context(materialization_path, MATERIALIZATION_SCHEMA)

    assert context["schema_version"] == "permitdiff.dev/r3-review-context/v1"
    assert context["cases"][0]["status"] == "pending"
    assert context["cases"][0]["documentation_refs"] == []
    serialized = json.dumps(context)
    assert "source_semantic_relation" not in serialized
    assert "source_semantics_resolution" not in serialized
    assert "tool_support" not in serialized
    assert "organizational_intent" not in serialized


def test_build_review_packets_creates_source_semantics_only_packets(tmp_path) -> None:
    materialization_path = _materialization(tmp_path / "source")
    context_path = _ready_context(materialization_path, tmp_path)
    output_dir = tmp_path / "packets"

    packet_set = build_review_packets(
        materialization_path,
        context_path,
        output_dir,
        MATERIALIZATION_SCHEMA,
        CONTEXT_SCHEMA,
        PACKET_SET_SCHEMA,
    )

    case = packet_set["cases"][0]
    transition_id = case["transition_id"]
    case_root = output_dir / "cases" / transition_id
    diff = (case_root / "source-diff.txt").read_text(encoding="utf-8")
    review = (case_root / "review.md").read_text(encoding="utf-8")
    serialized_packet = json.dumps(packet_set)

    assert packet_set["schema_version"] == "permitdiff.dev/r3-review-packet-set/v2"
    assert (
        packet_set["measurement_contract_version"]
        == "r3-exploratory-measurement-contract-v2"
    )
    assert packet_set["product_output_prohibited"] is True
    assert packet_set["review_scope"] == "source_semantics_only"
    assert set(packet_set["source_semantic_relation_definitions"]) == {
        "WIDENING",
        "RESTRICTIVE",
        "EQUIVALENT",
        "MIXED",
        "UNRESOLVED",
    }
    assert set(packet_set["source_semantics_resolution_definitions"]) == {
        "RESOLVED",
        "AMBIGUOUS",
        "UNAVAILABLE",
    }
    assert "SECURITY_RELEVANT_REGRESSION" not in serialized_packet
    assert "BENIGN_OR_RESTRICTIVE_CHANGE" not in serialized_packet
    assert "UNKNOWN_OR_UNSUPPORTED" not in serialized_packet
    assert "tool_support" not in packet_set
    assert "organizational_intent" not in packet_set

    assert "--- baseline.json" in diff
    assert "+++ candidate.json" in diff
    assert "Bash(*)" in diff
    assert "Do not consult PermitDiff output" in review
    assert "source_semantic_relation" in review
    assert "source_semantics_resolution" in review
    assert "tool support or organizational intent" in review
    assert "fixed-version semantic replay" in review
    assert "Public permission semantics" in review
    assert (case_root / "baseline.json").exists()
    assert (case_root / "candidate.json").exists()


def test_build_review_packets_rejects_pending_context(tmp_path) -> None:
    materialization_path = _materialization(tmp_path / "source")
    context = prepare_context(materialization_path, MATERIALIZATION_SCHEMA)
    context_path = tmp_path / "review-context.json"
    _write_json(context_path, context)

    with pytest.raises(ReviewPacketError, match="remains pending"):
        build_review_packets(
            materialization_path,
            context_path,
            tmp_path / "packets",
            MATERIALIZATION_SCHEMA,
            CONTEXT_SCHEMA,
            PACKET_SET_SCHEMA,
        )


def test_build_review_packets_rejects_context_bound_to_other_materialization(
    tmp_path,
) -> None:
    materialization_path = _materialization(tmp_path / "source")
    context_path = _ready_context(materialization_path, tmp_path)
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["source_materialization_sha256"] = "0" * 64
    _write_json(context_path, context)

    with pytest.raises(ReviewPacketError, match="not bound"):
        build_review_packets(
            materialization_path,
            context_path,
            tmp_path / "packets",
            MATERIALIZATION_SCHEMA,
            CONTEXT_SCHEMA,
            PACKET_SET_SCHEMA,
        )


def test_build_review_packets_rejects_tampered_materialized_artifact(tmp_path) -> None:
    materialization_path = _materialization(tmp_path / "source")
    context_path = _ready_context(materialization_path, tmp_path)
    materialization = json.loads(materialization_path.read_text(encoding="utf-8"))
    baseline_path = materialization["cases"][0]["baseline"]["path"]
    (materialization_path.parent / baseline_path).write_bytes(b'{"tampered": true}\n')

    with pytest.raises(ReviewPacketError, match="digest mismatch"):
        build_review_packets(
            materialization_path,
            context_path,
            tmp_path / "packets",
            MATERIALIZATION_SCHEMA,
            CONTEXT_SCHEMA,
            PACKET_SET_SCHEMA,
        )


def test_build_review_packets_requires_public_documentation(tmp_path) -> None:
    materialization_path = _materialization(tmp_path / "source")
    context = prepare_context(materialization_path, MATERIALIZATION_SCHEMA)
    context["cases"][0]["status"] = "ready"
    context_path = tmp_path / "review-context.json"
    _write_json(context_path, context)

    with pytest.raises(ReviewPacketError, match="no public source-system documentation"):
        build_review_packets(
            materialization_path,
            context_path,
            tmp_path / "packets",
            MATERIALIZATION_SCHEMA,
            CONTEXT_SCHEMA,
            PACKET_SET_SCHEMA,
        )


def test_build_review_packets_refuses_to_overwrite_packet_directory(tmp_path) -> None:
    materialization_path = _materialization(tmp_path / "source")
    context_path = _ready_context(materialization_path, tmp_path)
    output_dir = tmp_path / "packets"
    output_dir.mkdir()

    with pytest.raises(ReviewPacketError, match="refuse to overwrite packets"):
        build_review_packets(
            materialization_path,
            context_path,
            output_dir,
            MATERIALIZATION_SCHEMA,
            CONTEXT_SCHEMA,
            PACKET_SET_SCHEMA,
        )
