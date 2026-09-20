from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.lock_r3_exploratory_corpus import (
    PreExecutionLockError,
    create_pre_execution_lock,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = ROOT / "docs" / "r3-benchmark-case-manifest-v2.schema.json"
MATERIALIZATION_SCHEMA = ROOT / "docs" / "r3-public-materialization-v2.schema.json"
PACKET_SCHEMA = ROOT / "docs" / "r3-review-packet-set.schema.json"
ADJUDICATION_SCHEMA = ROOT / "docs" / "r3-adjudications.schema.json"
LOCK_SCHEMA = ROOT / "docs" / "r3-pre-execution-lock.schema.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    transition_id = "gh-" + "1" * 20
    baseline = b'{"permissions":{"allow":["Read"]}}\n'
    candidate = b'{"permissions":{"allow":["Read","Bash(*)"]}}\n'
    case_root = root / "cases" / transition_id
    case_root.mkdir(parents=True)
    (case_root / "baseline.json").write_bytes(baseline)
    (case_root / "candidate.json").write_bytes(candidate)

    baseline_record = {
        "path": f"cases/{transition_id}/baseline.json",
        "sha256": _sha256(baseline),
        "source_url": (
            "https://github.com/public/example/blob/" + "a" * 40 + "/.claude/settings.json"
        ),
        "source_commit": "a" * 40,
        "source_blob": "b" * 40,
        "size_bytes": len(baseline),
    }
    candidate_record = {
        "path": f"cases/{transition_id}/candidate.json",
        "sha256": _sha256(candidate),
        "source_url": (
            "https://github.com/public/example/blob/" + "c" * 40 + "/.claude/settings.json"
        ),
        "source_commit": "c" * 40,
        "source_blob": "d" * 40,
        "size_bytes": len(candidate),
    }

    materialization = {
        "schema_version": "permitdiff.dev/r3-public-materialization/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_selection_sha256": "e" * 64,
        "source_cb01_lineage_sha256": "f" * 64,
        "study_repository_commit": "4" * 40,
        "generated_at": "2026-09-01T00:00:00Z",
        "selected_case_count": 1,
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_full_name": "public/example",
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "f" * 64,
                "baseline": baseline_record,
                "candidate": candidate_record,
            }
        ],
    }
    materialization_path = root / "materialization.json"
    _write_json(materialization_path, materialization)

    packet = {
        "schema_version": "permitdiff.dev/r3-review-packet-set/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
        "source_materialization_sha256": _sha256(materialization_path.read_bytes()),
        "generated_at": "2026-09-01T00:00:01Z",
        "product_output_prohibited": True,
        "review_scope": "source_semantics_only",
        "source_semantic_question": "What source-semantic relation holds?",
        "source_semantic_relation_definitions": {
            "WIDENING": "widening",
            "RESTRICTIVE": "restrictive",
            "EQUIVALENT": "equivalent",
            "MIXED": "mixed",
            "UNRESOLVED": "unresolved",
        },
        "source_semantics_resolution_definitions": {
            "RESOLVED": "resolved",
            "AMBIGUOUS": "ambiguous",
            "UNAVAILABLE": "unavailable",
        },
        "case_count": 1,
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "f" * 64,
                "documentation_refs": [
                    {
                        "url": "https://docs.example.test/permissions",
                        "title": "Permission semantics",
                        "version_or_date": None,
                        "notes": None,
                    }
                ],
                "context_notes": None,
                "baseline": baseline_record,
                "candidate": candidate_record,
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
    _write_json(packet_path, packet)

    decision = {
        "rank": 1,
        "transition_id": transition_id,
        "status": "decided",
        "source_semantic_relation": "WIDENING",
        "tool_support": "UNSUPPORTED",
        "organizational_intent": "UNAVAILABLE",
        "source_semantics_resolution": "RESOLVED",
        "review_status": "single_reviewed",
        "reviewers": ["exploratory-reviewer-a"],
        "rationale": "Candidate adds documented Bash preapproval.",
        "atomic_categories": ["tool_or_scope_addition"],
        "evidence_refs": ["https://docs.example.test/permissions"],
        "ambiguity_notes": None,
        "change_family": "tool_or_scope_change",
        "blinding_state": "OUTPUT_BLIND",
        "contamination_state": "NO_KNOWN_PREEXPOSURE",
    }
    adjudications = {
        "schema_version": "permitdiff.dev/r3-adjudications/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
        "source_review_packet_set_sha256": _sha256(packet_path.read_bytes()),
        "generated_at": "2026-09-01T00:00:02Z",
        "product_output_consulted": False,
        "cases": [decision],
    }
    adjudications_path = root / "adjudications.json"
    _write_json(adjudications_path, adjudications)

    def _manifest_artifact(record: dict[str, object]) -> dict[str, object]:
        return {
            key: record[key]
            for key in ("path", "sha256", "source_url", "source_commit", "source_blob")
        }

    manifest = {
        "schema_version": "permitdiff.dev/r3-benchmark-case-manifest/v2",
        "protocol_version": "r3-benchmark-protocol-v1",
        "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
        "corpus_id": "r3-exploratory-public-historical-v1",
        "phase": "exploratory",
        "description": "test",
        "frozen_at": "2026-09-01T00:00:03Z",
        "cases": [
            {
                "id": transition_id,
                "source_kind": "public_historical",
                "source_system": "claude-code",
                "change_family": "tool_or_scope_change",
                "adapter": "claude-code-project-preapprovals",
                "description": "test transition",
                "notes": None,
                "tags": ["public-historical"],
                "baseline": _manifest_artifact(baseline_record),
                "candidate": _manifest_artifact(candidate_record),
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
        ],
    }
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path, materialization_path, packet_path, adjudications_path


def _lock(root: Path, output: Path):
    manifest, materialization, packet, adjudications = _fixture(root)
    return create_pre_execution_lock(
        manifest_path=manifest,
        materialization_path=materialization,
        review_packet_set_path=packet,
        adjudications_path=adjudications,
        output_dir=output,
        manifest_schema_path=MANIFEST_SCHEMA,
        materialization_schema_path=MATERIALIZATION_SCHEMA,
        packet_schema_path=PACKET_SCHEMA,
        adjudication_schema_path=ADJUDICATION_SCHEMA,
        lock_schema_path=LOCK_SCHEMA,
    )


def test_pre_execution_lock_accepts_v2_multidimensional_chain(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    lock = _lock(root, root / "pre-execution-lock-v1")

    assert lock["product_execution_performed"] is False
    assert lock["case_count"] == 1
    assert lock["manifest_integrity_validator_version"] == ("permitdiff-r3-benchmark-integrity-v1")
    assert (root / "pre-execution-lock-v1" / "manifest-integrity.json").exists()
    assert (root / "pre-execution-lock-v1" / "pre-execution-lock.json").exists()


def test_pre_execution_lock_rejects_existing_product_result(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    manifest, materialization, packet, adjudications = _fixture(root)
    (root / "permitdiff-results.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(PreExecutionLockError, match="product execution artifact"):
        create_pre_execution_lock(
            manifest_path=manifest,
            materialization_path=materialization,
            review_packet_set_path=packet,
            adjudications_path=adjudications,
            output_dir=root / "pre-execution-lock-v1",
            manifest_schema_path=MANIFEST_SCHEMA,
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            lock_schema_path=LOCK_SCHEMA,
        )


def test_pre_execution_lock_rejects_manifest_adjudication_drift(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    manifest, materialization, packet, adjudications = _fixture(root)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["cases"][0]["adjudication"]["tool_support"] = "SUPPORTED"
    _write_json(manifest, payload)

    with pytest.raises(PreExecutionLockError, match="adjudication mismatch"):
        create_pre_execution_lock(
            manifest_path=manifest,
            materialization_path=materialization,
            review_packet_set_path=packet,
            adjudications_path=adjudications,
            output_dir=root / "pre-execution-lock-v1",
            manifest_schema_path=MANIFEST_SCHEMA,
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            lock_schema_path=LOCK_SCHEMA,
        )


def test_pre_execution_lock_rejects_measurement_contract_version_drift(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    manifest, materialization, packet, adjudications = _fixture(root)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["measurement_contract_version"] = "wrong-contract"
    _write_json(manifest, payload)

    with pytest.raises(
        PreExecutionLockError,
        match=r"schema validation failed|measurement contract version mismatch",
    ):
        create_pre_execution_lock(
            manifest_path=manifest,
            materialization_path=materialization,
            review_packet_set_path=packet,
            adjudications_path=adjudications,
            output_dir=root / "pre-execution-lock-v1",
            manifest_schema_path=MANIFEST_SCHEMA,
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            lock_schema_path=LOCK_SCHEMA,
        )


def test_pre_execution_lock_rejects_tampered_source_artifact(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    manifest, materialization, packet, adjudications = _fixture(root)
    transition_id = "gh-" + "1" * 20
    (root / "cases" / transition_id / "candidate.json").write_text(
        '{"tampered":true}\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        create_pre_execution_lock(
            manifest_path=manifest,
            materialization_path=materialization,
            review_packet_set_path=packet,
            adjudications_path=adjudications,
            output_dir=root / "pre-execution-lock-v1",
            manifest_schema_path=MANIFEST_SCHEMA,
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            lock_schema_path=LOCK_SCHEMA,
        )


def test_pre_execution_lock_refuses_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    manifest, materialization, packet, adjudications = _fixture(root)
    output = root / "pre-execution-lock-v1"
    output.mkdir()

    with pytest.raises(PreExecutionLockError, match="refuse to overwrite lock evidence"):
        create_pre_execution_lock(
            manifest_path=manifest,
            materialization_path=materialization,
            review_packet_set_path=packet,
            adjudications_path=adjudications,
            output_dir=output,
            manifest_schema_path=MANIFEST_SCHEMA,
            materialization_schema_path=MATERIALIZATION_SCHEMA,
            packet_schema_path=PACKET_SCHEMA,
            adjudication_schema_path=ADJUDICATION_SCHEMA,
            lock_schema_path=LOCK_SCHEMA,
        )


# ---------------------------------------------------------------------------
# Packet C — materialization v2 + lineage/study gates (synthetic, no network)
# ---------------------------------------------------------------------------


def _packet_c_mutated_index(root: Path, mutate) -> tuple[Path, Path]:
    _, materialization, _, _ = _fixture(root)
    index = json.loads(materialization.read_text(encoding="utf-8"))
    mutate(index)
    materialization.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return materialization, root / "pre-execution-lock-v1"


def _packet_c_lock(materialization: Path, output: Path) -> None:
    root = materialization.parent
    manifest = root / "manifest.json"
    packet = root / "review-packets.json"
    adjudications = root / "adjudications.json"
    create_pre_execution_lock(
        manifest_path=manifest,
        materialization_path=materialization,
        review_packet_set_path=packet,
        adjudications_path=adjudications,
        output_dir=output,
        manifest_schema_path=MANIFEST_SCHEMA,
        materialization_schema_path=MATERIALIZATION_SCHEMA,
        packet_schema_path=PACKET_SCHEMA,
        adjudication_schema_path=ADJUDICATION_SCHEMA,
        lock_schema_path=LOCK_SCHEMA,
    )


def test_packet_c_rejects_v1_materialization(tmp_path: Path) -> None:
    def _to_v1(index: dict) -> None:
        index["schema_version"] = "permitdiff.dev/r3-public-materialization/v1"
        del index["source_cb01_lineage_sha256"]
        del index["study_repository_commit"]

    root = tmp_path / "corpus"
    materialization, output = _packet_c_mutated_index(root, _to_v1)
    with pytest.raises(PreExecutionLockError, match=r"schema validation failed|unsupported"):
        _packet_c_lock(materialization, output)
    assert not output.exists()


def test_packet_c_rejects_malformed_lineage_or_study(tmp_path: Path) -> None:
    for field, bad in (
        ("source_cb01_lineage_sha256", "not-a-digest"),
        ("study_repository_commit", "Z" * 40),
    ):
        def _mutate(index: dict, field: str = field, bad: str = bad) -> None:
            index[field] = bad

        root = tmp_path / field
        materialization, output = _packet_c_mutated_index(root, _mutate)
        with pytest.raises(
            PreExecutionLockError, match=r"schema validation failed|invalid"
        ):
            _packet_c_lock(materialization, output)
        assert not output.exists()
