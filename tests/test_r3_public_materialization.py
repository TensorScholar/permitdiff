from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.discover_r3_benchmark_candidates import selection_key, transition_id
from scripts.materialize_r3_public_selection import (
    MaterializationError,
    materialize_selection,
)

ROOT = Path(__file__).resolve().parents[1]
SELECTION_SCHEMA = ROOT / "docs" / "r3-public-selection.schema.json"
MATERIALIZATION_SCHEMA = ROOT / "docs" / "r3-public-materialization.schema.json"


class FakeClient:
    def __init__(
        self,
        baseline: bytes,
        candidate: bytes,
        *,
        private: bool = False,
        full_name: str = "public/example",
        baseline_blob: str = "c" * 40,
        candidate_blob: str = "d" * 40,
    ) -> None:
        self.baseline = baseline
        self.candidate = candidate
        self.private = private
        self.full_name = full_name
        self.baseline_blob = baseline_blob
        self.candidate_blob = candidate_blob
        self.repository_calls = 0
        self.file_calls: list[tuple[str, str, str]] = []

    def get_json(self, endpoint: str, params=None):
        assert endpoint == "/repos/public/example"
        self.repository_calls += 1
        return {"full_name": self.full_name, "private": self.private}

    def get_file(self, repository: str, path: str, ref: str):
        self.file_calls.append((repository, path, ref))
        if ref == "a" * 40:
            return {"sha": self.baseline_blob}, self.baseline
        if ref == "b" * 40:
            return {"sha": self.candidate_blob}, self.candidate
        raise AssertionError(f"unexpected ref: {ref}")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _selection(baseline: bytes, candidate: bytes) -> dict[str, object]:
    repository_url = "https://github.com/public/example"
    path = ".claude/settings.json"
    baseline_commit = "a" * 40
    candidate_commit = "b" * 40
    key = selection_key(repository_url, baseline_commit, candidate_commit, path)
    return {
        "schema_version": "permitdiff.dev/r3-public-selection/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_ledger_sha256": "9" * 64,
        "target_cases": 18,
        "max_cases_per_repository": 2,
        "eligible_case_count": 1,
        "selected_case_count": 1,
        "shortfall": 17,
        "selected": [
            {
                "rank": 1,
                "transition_id": transition_id(
                    repository_url,
                    baseline_commit,
                    candidate_commit,
                    path,
                ),
                "repository_full_name": "public/example",
                "repository_url": repository_url,
                "path": path,
                "baseline_commit": baseline_commit,
                "candidate_commit": candidate_commit,
                "baseline_blob": "c" * 40,
                "candidate_blob": "d" * 40,
                "baseline_sha256": _sha256(baseline),
                "candidate_sha256": _sha256(candidate),
                "selection_key": key,
            }
        ],
    }


def _write_selection(path: Path, baseline: bytes, candidate: bytes) -> None:
    path.write_text(
        json.dumps(_selection(baseline, candidate), indent=2) + "\n",
        encoding="utf-8",
    )


def test_materialize_selection_writes_exact_verified_public_bytes(tmp_path) -> None:
    baseline = b'{"permissions":{"allow":["Read"]}}\n'
    candidate = b'{"permissions":{"allow":["Read","Bash(*)"]}}\n'
    selection_path = tmp_path / "selection.json"
    output_dir = tmp_path / "materialized"
    _write_selection(selection_path, baseline, candidate)
    client = FakeClient(baseline, candidate)

    index = materialize_selection(
        selection_path,
        output_dir,
        SELECTION_SCHEMA,
        MATERIALIZATION_SCHEMA,
        client,
    )

    case = index["cases"][0]
    transition = case["transition_id"]
    assert (output_dir / f"cases/{transition}/baseline.json").read_bytes() == baseline
    assert (output_dir / f"cases/{transition}/candidate.json").read_bytes() == candidate
    assert json.loads((output_dir / "materialization.json").read_text()) == index
    assert client.repository_calls == 1
    assert len(client.file_calls) == 2
    assert case["baseline"]["source_commit"] == "a" * 40
    assert case["candidate"]["source_blob"] == "d" * 40


def test_materialize_selection_rejects_repository_that_is_not_public(tmp_path) -> None:
    baseline = b'{"permissions":{}}\n'
    candidate = b'{"permissions":{"allow":["Read"]}}\n'
    selection_path = tmp_path / "selection.json"
    output_dir = tmp_path / "materialized"
    _write_selection(selection_path, baseline, candidate)

    with pytest.raises(MaterializationError, match="not explicitly public"):
        materialize_selection(
            selection_path,
            output_dir,
            SELECTION_SCHEMA,
            MATERIALIZATION_SCHEMA,
            FakeClient(baseline, candidate, private=True),
        )

    assert not output_dir.exists()


def test_materialize_selection_rejects_changed_repository_identity(tmp_path) -> None:
    baseline = b'{"permissions":{}}\n'
    candidate = b'{"permissions":{"allow":["Read"]}}\n'
    selection_path = tmp_path / "selection.json"
    output_dir = tmp_path / "materialized"
    _write_selection(selection_path, baseline, candidate)

    with pytest.raises(MaterializationError, match="identity changed"):
        materialize_selection(
            selection_path,
            output_dir,
            SELECTION_SCHEMA,
            MATERIALIZATION_SCHEMA,
            FakeClient(baseline, candidate, full_name="public/renamed"),
        )

    assert not output_dir.exists()


def test_materialize_selection_rejects_blob_mismatch_without_publishing_partial_output(
    tmp_path,
) -> None:
    baseline = b'{"permissions":{}}\n'
    candidate = b'{"permissions":{"allow":["Read"]}}\n'
    selection_path = tmp_path / "selection.json"
    output_dir = tmp_path / "materialized"
    _write_selection(selection_path, baseline, candidate)

    with pytest.raises(MaterializationError, match="blob mismatch"):
        materialize_selection(
            selection_path,
            output_dir,
            SELECTION_SCHEMA,
            MATERIALIZATION_SCHEMA,
            FakeClient(baseline, candidate, baseline_blob="e" * 40),
        )

    assert not output_dir.exists()


def test_materialize_selection_rejects_sha256_mismatch(tmp_path) -> None:
    baseline = b'{"permissions":{}}\n'
    candidate = b'{"permissions":{"allow":["Read"]}}\n'
    selection_path = tmp_path / "selection.json"
    output_dir = tmp_path / "materialized"
    _write_selection(selection_path, baseline, candidate)
    client = FakeClient(baseline + b" ", candidate)

    with pytest.raises(MaterializationError, match="SHA-256 mismatch"):
        materialize_selection(
            selection_path,
            output_dir,
            SELECTION_SCHEMA,
            MATERIALIZATION_SCHEMA,
            client,
        )

    assert not output_dir.exists()


def test_materialize_selection_refuses_to_overwrite_existing_evidence_directory(
    tmp_path,
) -> None:
    baseline = b'{"permissions":{}}\n'
    candidate = b'{"permissions":{"allow":["Read"]}}\n'
    selection_path = tmp_path / "selection.json"
    output_dir = tmp_path / "materialized"
    output_dir.mkdir()
    _write_selection(selection_path, baseline, candidate)

    with pytest.raises(MaterializationError, match="refuse to overwrite evidence"):
        materialize_selection(
            selection_path,
            output_dir,
            SELECTION_SCHEMA,
            MATERIALIZATION_SCHEMA,
            FakeClient(baseline, candidate),
        )


def test_materialize_selection_rejects_noncontiguous_selection_ranks(tmp_path) -> None:
    baseline = b'{"permissions":{}}\n'
    candidate = b'{"permissions":{"allow":["Read"]}}\n'
    selection = _selection(baseline, candidate)
    selection["selected"][0]["rank"] = 2
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection) + "\n", encoding="utf-8")

    with pytest.raises(MaterializationError, match="ranks must be contiguous"):
        materialize_selection(
            selection_path,
            tmp_path / "materialized",
            SELECTION_SCHEMA,
            MATERIALIZATION_SCHEMA,
            FakeClient(baseline, candidate),
        )
