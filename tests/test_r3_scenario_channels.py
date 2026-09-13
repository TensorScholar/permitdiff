from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_r3_scenario_channels import (
    ScenarioChannelError,
    prepare_scenario_channels,
    validate_scenario_channels,
)

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZATION_SCHEMA = ROOT / "docs" / "r3-public-materialization.schema.json"
SCENARIO_SCHEMA = ROOT / "docs" / "r3-scenario-channel-set.schema.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _materialization(root: Path) -> Path:
    transition_id = "gh-" + "1" * 20
    baseline = b'{"permissions":{"allow":["Read"]}}\n'
    candidate = b'{"permissions":{"allow":["Read","WebSearch"]}}\n'
    case_root = root / "cases" / transition_id
    case_root.mkdir(parents=True)
    (case_root / "baseline.json").write_bytes(baseline)
    (case_root / "candidate.json").write_bytes(candidate)
    payload = {
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
                    "source_url": "https://github.com/public/example/blob/"
                    + "c" * 40
                    + "/.claude/settings.json",
                    "source_commit": "c" * 40,
                    "source_blob": "d" * 40,
                    "size_bytes": len(baseline),
                },
                "candidate": {
                    "path": f"cases/{transition_id}/candidate.json",
                    "sha256": _sha256(candidate),
                    "source_url": "https://github.com/public/example/blob/"
                    + "e" * 40
                    + "/.claude/settings.json",
                    "source_commit": "e" * 40,
                    "source_blob": "f" * 40,
                    "size_bytes": len(candidate),
                },
            }
        ],
    }
    path = root / "materialization.json"
    _write_json(path, payload)
    return path


def _prepared(materialization: Path, tmp_path: Path) -> tuple[dict[str, object], Path]:
    payload = prepare_scenario_channels(materialization, MATERIALIZATION_SCHEMA)
    path = tmp_path / "scenario-channels.json"
    _write_json(path, payload)
    return payload, path


def _scenario_set(root: Path, *, provenance: str, name: str = "primary.jsonl") -> dict[str, object]:
    transition_id = "gh-" + "1" * 20
    relative = f"cases/{transition_id}/scenarios/{name}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = b'{"id":"scenario-1","tool":"WebSearch"}\n'
    path.write_bytes(payload)
    return {
        "id": name.replace(".", "-"),
        "provenance": provenance,
        "primary_admissible": provenance in {"PREEXISTING_PROJECT", "INDEPENDENT_BLIND"},
        "artifact": {
            "path": relative,
            "sha256": _sha256(payload),
            "source_url": "https://github.com/public/example/blob/" + "a" * 40 + "/scenarios.jsonl",
            "source_commit": "a" * 40,
            "source_blob": "b" * 40,
        },
        "provenance_evidence_refs": ["https://github.com/public/example/commit/" + "a" * 40],
        "generation_cost_accounting_required": provenance == "PRODUCT_GENERATED",
        "notes": None,
    }


def _validate(materialization: Path, scenario_path: Path) -> dict[str, object]:
    return validate_scenario_channels(
        materialization,
        scenario_path,
        materialization_schema_path=MATERIALIZATION_SCHEMA,
        scenario_schema_path=SCENARIO_SCHEMA,
    )


def test_prepare_is_bound_pending_and_does_not_create_scenario_files(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)

    prepared = prepare_scenario_channels(materialization, MATERIALIZATION_SCHEMA)

    assert prepared["schema_version"] == "permitdiff.dev/r3-scenario-channel-set/v1"
    assert prepared["product_output_consulted"] is False
    assert prepared["source_materialization_sha256"] == _sha256(materialization.read_bytes())
    assert prepared["cases"][0]["status"] == "pending"
    assert prepared["cases"][0]["primary_channel_state"] is None
    assert prepared["cases"][0]["scenario_sets"] == []
    assert not (root / "cases" / ("gh-" + "1" * 20) / "scenarios").exists()


def test_explicit_absent_primary_channel_is_valid_without_placeholder_corpus(
    tmp_path: Path,
) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)
    payload, scenario_path = _prepared(materialization, tmp_path)
    case = payload["cases"][0]
    case.update(
        {
            "status": "decided",
            "primary_channel_state": "ABSENT",
            "absence_reason": "NO_PRIMARY_ADMISSIBLE_SCENARIO_SET",
            "notes": "No pre-existing or independently blind corpus was available.",
        }
    )
    _write_json(scenario_path, payload)

    evidence = _validate(materialization, scenario_path)

    assert evidence["primary_absent_count"] == 1
    assert evidence["primary_present_count"] == 0
    assert evidence["primary_scenario_set_count"] == 0


def test_preexisting_project_scenario_makes_primary_channel_present(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)
    payload, scenario_path = _prepared(materialization, tmp_path)
    case = payload["cases"][0]
    case.update(
        {
            "status": "decided",
            "primary_channel_state": "PRESENT",
            "scenario_sets": [_scenario_set(root, provenance="PREEXISTING_PROJECT")],
        }
    )
    _write_json(scenario_path, payload)

    evidence = _validate(materialization, scenario_path)

    assert evidence["primary_present_count"] == 1
    assert evidence["primary_scenario_set_count"] == 1
    assert evidence["diagnostic_scenario_set_count"] == 0


def test_answer_informed_scenario_is_diagnostic_and_primary_channel_stays_absent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)
    payload, scenario_path = _prepared(materialization, tmp_path)
    case = payload["cases"][0]
    case.update(
        {
            "status": "decided",
            "primary_channel_state": "ABSENT",
            "absence_reason": "NO_PRIMARY_ADMISSIBLE_SCENARIO_SET",
            "scenario_sets": [
                _scenario_set(
                    root,
                    provenance="DIAGNOSTIC_ANSWER_INFORMED",
                    name="diagnostic.jsonl",
                )
            ],
        }
    )
    _write_json(scenario_path, payload)

    evidence = _validate(materialization, scenario_path)

    assert evidence["primary_absent_count"] == 1
    assert evidence["diagnostic_scenario_set_count"] == 1


def test_answer_informed_scenario_cannot_be_used_to_claim_primary_presence(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)
    payload, scenario_path = _prepared(materialization, tmp_path)
    case = payload["cases"][0]
    case.update(
        {
            "status": "decided",
            "primary_channel_state": "PRESENT",
            "scenario_sets": [
                _scenario_set(
                    root,
                    provenance="DIAGNOSTIC_ANSWER_INFORMED",
                    name="diagnostic.jsonl",
                )
            ],
        }
    )
    _write_json(scenario_path, payload)

    with pytest.raises(ScenarioChannelError, match="must be ABSENT"):
        _validate(materialization, scenario_path)


def test_product_generated_scenario_is_rejected_before_preexecution_lock(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)
    payload, scenario_path = _prepared(materialization, tmp_path)
    case = payload["cases"][0]
    case.update(
        {
            "status": "decided",
            "primary_channel_state": "ABSENT",
            "absence_reason": "NO_PRIMARY_ADMISSIBLE_SCENARIO_SET",
            "scenario_sets": [
                _scenario_set(root, provenance="PRODUCT_GENERATED", name="generated.jsonl")
            ],
        }
    )
    _write_json(scenario_path, payload)

    with pytest.raises(ScenarioChannelError, match="cannot exist in the pre-execution"):
        _validate(materialization, scenario_path)


def test_tampered_scenario_artifact_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    materialization = _materialization(root)
    payload, scenario_path = _prepared(materialization, tmp_path)
    scenario_set = _scenario_set(root, provenance="INDEPENDENT_BLIND")
    case = payload["cases"][0]
    case.update(
        {
            "status": "decided",
            "primary_channel_state": "PRESENT",
            "scenario_sets": [scenario_set],
        }
    )
    _write_json(scenario_path, payload)
    artifact_path = root / scenario_set["artifact"]["path"]
    artifact_path.write_text('{"tampered":true}\n', encoding="utf-8")

    with pytest.raises(ScenarioChannelError, match="SHA-256 mismatch"):
        _validate(materialization, scenario_path)
