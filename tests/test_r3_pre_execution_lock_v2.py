from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import scripts.lock_r3_exploratory_corpus_v2 as lock_v2
from scripts.lock_r3_exploratory_corpus import PreExecutionLockError

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_CONTRACT = (
    ROOT / "validation" / "r3-benchmark" / "exploratory" / "measurement-contract-v2.json"
)
MEASUREMENT_SCHEMA = ROOT / "docs" / "r3-measurement-contract.schema.json"
LOCK_V2_SCHEMA = ROOT / "docs" / "r3-pre-execution-lock-v2.schema.json"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True)
    transition_id = "gh-" + "1" * 20
    paths = {
        "manifest": root / "manifest.json",
        "materialization": root / "materialization.json",
        "review_packets": root / "review-packets.json",
        "adjudications": root / "adjudications.json",
        "measurement_contract": root / "measurement-contract-v2.json",
        "scenario_channels": root / "scenario-channels-v1.json",
    }

    case_root = root / "cases" / transition_id
    case_root.mkdir(parents=True)
    baseline = b'{"permissions":{"allow":["Read"]}}\n'
    candidate = b'{"permissions":{"allow":["Read","Bash(*)"]}}\n'
    source_diff = b"--- baseline.json\n+++ candidate.json\n"
    review_markdown = b"# blinded review\n"
    (case_root / "baseline.json").write_bytes(baseline)
    (case_root / "candidate.json").write_bytes(candidate)
    (case_root / "source-diff.txt").write_bytes(source_diff)
    (case_root / "review.md").write_bytes(review_markdown)

    def artifact(role: str, payload: bytes) -> dict[str, object]:
        return {
            "path": f"cases/{transition_id}/{role}.json",
            "sha256": _sha256(payload),
            "source_url": f"https://github.com/public/example/{role}",
            "source_commit": ("a" if role == "baseline" else "b") * 40,
            "source_blob": ("c" if role == "baseline" else "d") * 40,
            "size_bytes": len(payload),
        }

    baseline_record = artifact("baseline", baseline)
    candidate_record = artifact("candidate", candidate)
    materialization = {
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "e" * 64,
                "baseline": baseline_record,
                "candidate": candidate_record,
            }
        ]
    }
    _write_json(paths["materialization"], materialization)

    review_packets = {
        "source_materialization_sha256": _sha256(paths["materialization"].read_bytes()),
        "cases": [
            {
                "rank": 1,
                "transition_id": transition_id,
                "repository_url": "https://github.com/public/example",
                "source_path": ".claude/settings.json",
                "selection_key": "e" * 64,
                "baseline": baseline_record,
                "candidate": candidate_record,
                "source_diff": {
                    "path": f"cases/{transition_id}/source-diff.txt",
                    "sha256": _sha256(source_diff),
                },
                "review_markdown": {
                    "path": f"cases/{transition_id}/review.md",
                    "sha256": _sha256(review_markdown),
                },
            }
        ],
    }
    _write_json(paths["review_packets"], review_packets)

    _write_json(paths["manifest"], {"corpus_id": "r3-test"})
    _write_json(paths["adjudications"], {"cases": [{"transition_id": transition_id}]})
    shutil.copyfile(MEASUREMENT_CONTRACT, paths["measurement_contract"])
    _write_json(
        paths["scenario_channels"],
        {
            "schema_version": "permitdiff.dev/r3-scenario-channel-set/v1",
            "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
            "case_count": 1,
            "cases": [{"transition_id": transition_id, "status": "decided"}],
        },
    )
    return paths


def _install_stubs(monkeypatch: pytest.MonkeyPatch, paths: dict[str, Path]) -> None:
    def fake_scenario_integrity(*args, **kwargs):
        payload = paths["scenario_channels"].read_bytes()
        return {
            "schema_version": "permitdiff.dev/r3-scenario-channel-set/v1",
            "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
            "source_materialization_sha256": "a" * 64,
            "scenario_channel_set_sha256": _sha256(payload),
            "case_count": 1,
            "primary_present_count": 0,
            "primary_absent_count": 1,
            "primary_scenario_set_count": 0,
            "diagnostic_scenario_set_count": 0,
            "product_output_consulted": False,
        }

    def fake_legacy_lock(*, output_dir: Path, **kwargs):
        output_dir.mkdir(parents=True)
        integrity = {
            "validator_version": "permitdiff-r3-benchmark-integrity-v1",
            "case_count": 1,
        }
        _write_json(output_dir / "manifest-integrity.json", integrity)
        return {
            "plan_version": "r3-exploratory-corpus-plan-v1",
            "protocol_version": "r3-benchmark-protocol-v1",
            "corpus_id": "r3-test",
            "case_count": 1,
            "manifest_sha256": _sha256(paths["manifest"].read_bytes()),
            "materialization_sha256": _sha256(paths["materialization"].read_bytes()),
            "review_packet_set_sha256": _sha256(paths["review_packets"].read_bytes()),
            "adjudications_sha256": _sha256(paths["adjudications"].read_bytes()),
            "manifest_integrity_validator_version": "permitdiff-r3-benchmark-integrity-v1",
        }

    monkeypatch.setattr(lock_v2, "validate_scenario_channels", fake_scenario_integrity)
    monkeypatch.setattr(lock_v2, "create_legacy_pre_execution_lock", fake_legacy_lock)


def _create(
    paths: dict[str, Path], output: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    _install_stubs(monkeypatch, paths)
    placeholder_schema = ROOT / "docs" / "r3-pre-execution-lock.schema.json"
    return lock_v2.create_complete_pre_execution_lock(
        manifest_path=paths["manifest"],
        materialization_path=paths["materialization"],
        review_packet_set_path=paths["review_packets"],
        adjudications_path=paths["adjudications"],
        measurement_contract_path=paths["measurement_contract"],
        scenario_channel_set_path=paths["scenario_channels"],
        output_dir=output,
        manifest_schema_path=placeholder_schema,
        materialization_schema_path=placeholder_schema,
        packet_schema_path=placeholder_schema,
        adjudication_schema_path=placeholder_schema,
        measurement_contract_schema_path=MEASUREMENT_SCHEMA,
        scenario_channel_schema_path=placeholder_schema,
        legacy_lock_schema_path=placeholder_schema,
        lock_schema_path=LOCK_V2_SCHEMA,
    )


def test_v2_lock_binds_exact_measurement_and_scenario_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path / "evidence")
    output = tmp_path / "evidence" / "pre-execution-lock-v2"

    lock = _create(paths, output, monkeypatch)

    assert lock["schema_version"] == "permitdiff.dev/r3-pre-execution-lock/v2"
    assert lock["measurement_contract_sha256"] == _sha256(
        paths["measurement_contract"].read_bytes()
    )
    assert lock["scenario_channel_set_sha256"] == _sha256(
        paths["scenario_channels"].read_bytes()
    )
    assert lock["product_execution_performed"] is False
    assert (output / "manifest-integrity.json").exists()
    scenario_integrity = output / "scenario-channel-integrity.json"
    assert scenario_integrity.exists()
    assert lock["scenario_channel_integrity_sha256"] == _sha256(
        scenario_integrity.read_bytes()
    )
    assert (output / "pre-execution-lock.json").exists()


def test_v2_lock_rejects_measurement_contract_semantic_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path / "evidence")
    contract = json.loads(paths["measurement_contract"].read_text(encoding="utf-8"))
    contract["review_trigger_scoring_contract"]["relation_trigger_policy"]["UNRESOLVED"] = (
        "NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE"
    )
    _write_json(paths["measurement_contract"], contract)
    _install_stubs(monkeypatch, paths)

    with pytest.raises(PreExecutionLockError, match="measurement contract schema validation"):
        _create(paths, tmp_path / "evidence" / "pre-execution-lock-v2", monkeypatch)


def test_v2_lock_rejects_scenario_integrity_digest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path / "evidence")
    _install_stubs(monkeypatch, paths)

    def bad_scenario_integrity(*args, **kwargs):
        return {
            "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
            "scenario_channel_set_sha256": "0" * 64,
            "case_count": 1,
        }

    monkeypatch.setattr(lock_v2, "validate_scenario_channels", bad_scenario_integrity)
    placeholder_schema = ROOT / "docs" / "r3-pre-execution-lock.schema.json"
    with pytest.raises(PreExecutionLockError, match="scenario channel integrity digest mismatch"):
        lock_v2.create_complete_pre_execution_lock(
            manifest_path=paths["manifest"],
            materialization_path=paths["materialization"],
            review_packet_set_path=paths["review_packets"],
            adjudications_path=paths["adjudications"],
            measurement_contract_path=paths["measurement_contract"],
            scenario_channel_set_path=paths["scenario_channels"],
            output_dir=tmp_path / "evidence" / "pre-execution-lock-v2",
            manifest_schema_path=placeholder_schema,
            materialization_schema_path=placeholder_schema,
            packet_schema_path=placeholder_schema,
            adjudication_schema_path=placeholder_schema,
            measurement_contract_schema_path=MEASUREMENT_SCHEMA,
            scenario_channel_schema_path=placeholder_schema,
            legacy_lock_schema_path=placeholder_schema,
            lock_schema_path=LOCK_V2_SCHEMA,
        )


def test_v2_lock_rejects_preexisting_product_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path / "evidence")
    (tmp_path / "evidence" / "permitdiff-results.json").write_text("{}\n", encoding="utf-8")
    _install_stubs(monkeypatch, paths)

    with pytest.raises(PreExecutionLockError, match="product execution artifact"):
        _create(paths, tmp_path / "evidence" / "pre-execution-lock-v2", monkeypatch)


def test_v2_lock_rejects_review_packet_artifact_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path / "evidence")
    transition_id = "gh-" + "1" * 20
    (
        tmp_path
        / "evidence"
        / "cases"
        / transition_id
        / "source-diff.txt"
    ).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(PreExecutionLockError, match="review packet .*source_diff SHA-256 mismatch"):
        _create(paths, tmp_path / "evidence" / "pre-execution-lock-v2", monkeypatch)


def test_v2_lock_rejects_review_packet_materialization_provenance_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _fixture(tmp_path / "evidence")
    packet_set = json.loads(paths["review_packets"].read_text(encoding="utf-8"))
    packet_set["cases"][0]["candidate"]["source_commit"] = "f" * 40
    _write_json(paths["review_packets"], packet_set)

    with pytest.raises(PreExecutionLockError, match="review packet candidate provenance mismatch"):
        _create(paths, tmp_path / "evidence" / "pre-execution-lock-v2", monkeypatch)
