#!/usr/bin/env python3
"""Create the deterministic R3 v3 pre-execution lock without executing PermitDiff."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from scripts.discover_r3_benchmark_candidates import select_public_historical
from scripts.lock_r3_exploratory_corpus import PreExecutionLockError
from scripts.lock_r3_exploratory_corpus_v2 import create_complete_pre_execution_lock
from scripts.r3_documentation_snapshots import documentation_set_digest, validate_manifest
from scripts.r3_execution_environment import load_lock as load_environment_lock
from scripts.r3_execution_environment import validate_source_artifacts
from scripts.r3_pre_discovery_contract import (
    MAX_CASES_PER_REPOSITORY,
    MINIMUM_CASES,
    TARGET_CASES,
    validate_selection_shape,
)
from scripts.r3_review_assignment import validate_balance

LOCK_SCHEMA_VERSION = "permitdiff.dev/r3-pre-execution-lock/v3"
HARDENING_CONTRACT_VERSION = "r3-pre-discovery-hardening-v1"
PRODUCT_COMMIT = "1f3b3a4afda67c01c4f29a93a45b18511980036b"

METHODOLOGY_COMPONENTS = (
    "docs/r3-benchmark-protocol.md",
    "docs/r3-exploratory-corpus-plan.md",
    "validation/r3-benchmark/exploratory/selection-plan.json",
    "docs/r3-measurement-contract-amendment.md",
    "validation/r3-benchmark/exploratory/measurement-contract-v2.json",
    "docs/r3-measurement-contract.schema.json",
    "docs/r3-review-trigger-scoring.md",
    "docs/r3-adjudications.md",
    "docs/r3-adjudications.schema.json",
    "docs/r3-benchmark-case-manifest-v2.schema.json",
    "docs/r3-review-packets.md",
    "docs/r3-review-context.schema.json",
    "docs/r3-review-packet-set.schema.json",
    "docs/r3-scenario-provenance.md",
    "docs/r3-scenario-channel-set.schema.json",
    "docs/r3-freeze-completion.md",
    "docs/r3-freeze-completion-contract.schema.json",
    "validation/r3-benchmark/exploratory/freeze-completion-contract-v1.json",
    "docs/r3-pre-discovery-hardening.md",
    "docs/r3-pre-discovery-hardening-contract.schema.json",
    "validation/r3-benchmark/exploratory/pre-discovery-hardening-contract-v1.json",
    "docs/r3-reviewer-protocol.schema.json",
    "validation/r3-benchmark/exploratory/reviewer-protocol-v1.json",
    "docs/r3-reviewer-roster.schema.json",
    "docs/r3-condition-assignment.schema.json",
    "docs/r3-documentation-snapshot-manifest.schema.json",
    "docs/r3-execution-environment-lock.schema.json",
    "validation/r3-benchmark/exploratory/permitdiff-execution-environment-v1.json",
    "validation/r3-benchmark/exploratory/r3-runtime-requirements-v1.lock",
    "validation/r3-benchmark/exploratory/r3-build-requirements-v1.lock",
    "docs/r3-freeze-completion-records-v2.schema.json",
    "docs/r3-study-result-set.schema.json",
    "docs/r3-pre-execution-lock-v3.schema.json",
    "scripts/discover_r3_benchmark_candidates.py",
    "scripts/discover_r3_public_benchmark_candidates.py",
    "scripts/screen_r3_public_benchmark_candidates.py",
    "scripts/materialize_r3_public_selection.py",
    "scripts/build_r3_blinded_review_packets.py",
    "scripts/build_r3_exploratory_adjudications.py",
    "scripts/build_r3_scenario_channels.py",
    "scripts/validate_r3_benchmark_manifest.py",
    "scripts/lock_r3_exploratory_corpus.py",
    "scripts/lock_r3_exploratory_corpus_v2.py",
    "scripts/r3_simple_native_baseline.py",
    "scripts/r3_pre_discovery_contract.py",
    "scripts/r3_review_assignment.py",
    "scripts/r3_documentation_snapshots.py",
    "scripts/r3_execution_environment.py",
    "scripts/r3_study_results.py",
    "scripts/lock_r3_exploratory_corpus_v3.py",
)


class V3LockError(PreExecutionLockError):
    """Raised when the amended R3 evidence state is not fully frozen."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    return _sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise V3LockError("git executable is unavailable")
    return executable


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise V3LockError(f"cannot read {label}: {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise V3LockError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise V3LockError(f"{label} must be a JSON object: {path}")
    return value, raw


def _validate_schema(value: dict[str, Any], schema_path: Path, label: str) -> None:
    schema, _ = _read_json(schema_path, f"{label} schema")
    Draft202012Validator.check_schema(schema)
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value), None
    )
    if error is not None:
        raise V3LockError(f"{label} schema validation failed: {error.message}")


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            [_git_executable(), "-C", str(repo), *args],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise V3LockError(f"git {' '.join(args)} failed: {exc.output}") from exc


def _assert_clean_repo(repo: Path) -> str:
    status = _git(repo, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise V3LockError("study repository must be clean before the v3 lock is created")
    return _git(repo, "rev-parse", "HEAD")


def _methodology_digests(repo: Path, head: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in METHODOLOGY_COMPONENTS:
        path = repo / relative
        if not path.is_file():
            raise V3LockError(f"required methodology component is missing: {relative}")
        working = path.read_bytes()
        try:
            tracked = subprocess.check_output(
                [_git_executable(), "-C", str(repo), "show", f"{head}:{relative}"],
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as exc:
            raise V3LockError(f"methodology component is not tracked at HEAD: {relative}") from exc
        if working != tracked:
            raise V3LockError(f"methodology component differs from HEAD: {relative}")
        result[relative] = _sha256(working)
    return result


def _case_map(payload: Mapping[str, Any], id_field: str) -> dict[str, Mapping[str, Any]]:
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(case, Mapping) for case in raw_cases):
        raise V3LockError("case-bearing artifact has malformed cases")
    result: dict[str, Mapping[str, Any]] = {}
    for case in raw_cases:
        case_id = case.get(id_field)
        if not isinstance(case_id, str) or not case_id:
            raise V3LockError(f"invalid {id_field} in case-bearing artifact")
        if case_id in result:
            raise V3LockError(f"duplicate case id: {case_id}")
        result[case_id] = case
    return result


def _primary_scenario_sha(case: Mapping[str, Any]) -> str | None:
    state = case.get("primary_channel_state")
    sets = case.get("scenario_sets")
    if not isinstance(sets, list):
        raise V3LockError("scenario_sets must be a list")
    primary = [
        item
        for item in sets
        if isinstance(item, Mapping) and item.get("primary_admissible") is True
    ]
    if state == "ABSENT":
        if primary:
            raise V3LockError("ABSENT scenario channel contains primary-admissible scenario set")
        return None
    if state != "PRESENT":
        raise V3LockError("all scenario-channel cases must be decided PRESENT or ABSENT")
    if len(primary) != 1:
        raise V3LockError(
            "PRESENT scenario channel must contain exactly one primary-admissible scenario set"
        )
    artifact = primary[0].get("artifact")
    if not isinstance(artifact, Mapping) or not isinstance(artifact.get("sha256"), str):
        raise V3LockError("primary scenario artifact is malformed")
    return str(artifact["sha256"])


def _validate_selection(
    ledger: dict[str, Any], selection: dict[str, Any], selection_bytes: bytes
) -> None:
    validate_selection_shape(selection)
    expected = select_public_historical(
        ledger,
        target=TARGET_CASES,
        max_per_repository=MAX_CASES_PER_REPOSITORY,
    )
    if expected != selection:
        raise V3LockError("selection is not the exact frozen deterministic selection")
    if selection["eligible_case_count"] < MINIMUM_CASES:
        raise V3LockError("natural corpus is below the frozen minimum viable count")
    if not selection_bytes.endswith(b"\n"):
        raise V3LockError("selection artifact must use canonical newline-terminated JSON evidence")


def create_v3_lock(
    *,
    repo: Path,
    screened_ledger_path: Path,
    selection_path: Path,
    manifest_path: Path,
    materialization_path: Path,
    review_packet_set_path: Path,
    adjudications_path: Path,
    measurement_contract_path: Path,
    scenario_channel_set_path: Path,
    documentation_snapshot_manifest_path: Path,
    reviewer_roster_path: Path,
    condition_assignment_path: Path,
    environment_lock_path: Path,
    freeze_completion_contract_path: Path,
    hardening_contract_path: Path,
    product_wheel_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Validate all pre-result contracts and return deterministic v3 lock content."""

    repo = repo.resolve()
    head = _assert_clean_repo(repo)
    methodology = _methodology_digests(repo, head)

    ledger, ledger_bytes = _read_json(screened_ledger_path, "screened discovery ledger")
    selection, selection_bytes = _read_json(selection_path, "public selection")
    _validate_selection(ledger, selection, selection_bytes)

    materialization, materialization_bytes = _read_json(materialization_path, "materialization")
    if materialization.get("source_selection_sha256") != _sha256(selection_bytes):
        raise V3LockError("materialization is not bound to the exact selection bytes")

    with tempfile.TemporaryDirectory(prefix="r3-v3-v2-validation-") as temp:
        root = repo
        create_complete_pre_execution_lock(
            manifest_path=manifest_path,
            materialization_path=materialization_path,
            review_packet_set_path=review_packet_set_path,
            adjudications_path=adjudications_path,
            measurement_contract_path=measurement_contract_path,
            scenario_channel_set_path=scenario_channel_set_path,
            output_dir=Path(temp) / "v2",
            manifest_schema_path=root / "docs/r3-benchmark-case-manifest-v2.schema.json",
            materialization_schema_path=root / "docs/r3-public-materialization.schema.json",
            packet_schema_path=root / "docs/r3-review-packet-set.schema.json",
            adjudication_schema_path=root / "docs/r3-adjudications.schema.json",
            measurement_contract_schema_path=root / "docs/r3-measurement-contract.schema.json",
            scenario_channel_schema_path=root / "docs/r3-scenario-channel-set.schema.json",
            legacy_lock_schema_path=root / "docs/r3-pre-execution-lock.schema.json",
            lock_schema_path=root / "docs/r3-pre-execution-lock-v2.schema.json",
        )

    manifest, manifest_bytes = _read_json(manifest_path, "manifest")
    packet_set, packet_bytes = _read_json(review_packet_set_path, "review packet set")
    adjudications, adjudication_bytes = _read_json(adjudications_path, "adjudications")
    scenarios, scenario_bytes = _read_json(scenario_channel_set_path, "scenario channel set")
    measurement, _measurement_bytes = _read_json(measurement_contract_path, "measurement contract")
    freeze_contract, _freeze_bytes = _read_json(
        freeze_completion_contract_path, "freeze-completion contract"
    )
    hardening, _hardening_bytes = _read_json(hardening_contract_path, "hardening contract")
    roster, roster_bytes = _read_json(reviewer_roster_path, "reviewer roster")
    assignment, assignment_bytes = _read_json(condition_assignment_path, "condition assignment")
    environment, environment_bytes = _read_json(environment_lock_path, "execution environment")
    try:
        product_wheel_sha256 = _sha256(product_wheel_path.read_bytes())
    except OSError as exc:
        raise V3LockError(
            f"cannot read frozen PermitDiff product wheel: {product_wheel_path}"
        ) from exc
    if product_wheel_path.suffix != ".whl":
        raise V3LockError("frozen PermitDiff product artifact must be a wheel")

    if hardening.get("contract_version") != HARDENING_CONTRACT_VERSION:
        raise V3LockError("hardening contract version mismatch")
    if freeze_contract.get("product_execution_commit") != PRODUCT_COMMIT:
        raise V3LockError("freeze-completion product commit mismatch")
    if environment.get("product_commit") != PRODUCT_COMMIT:
        raise V3LockError("execution-environment product commit mismatch")
    if measurement.get("measurement_contract_version") != "r3-exploratory-measurement-contract-v2":
        raise V3LockError("measurement contract version mismatch")

    environment_schema = repo / "docs/r3-execution-environment-lock.schema.json"
    environment = load_environment_lock(environment_lock_path, environment_schema)
    validate_source_artifacts(environment, repo)
    runtime_lock = environment["r3_dependency_locks"]["runtime"]
    build_lock = environment["r3_dependency_locks"]["build"]

    materialization_cases = list(_case_map(materialization, "transition_id").values())
    case_ids = [str(case["transition_id"]) for case in materialization_cases]
    if not (MINIMUM_CASES <= len(case_ids) <= TARGET_CASES):
        raise V3LockError("materialized natural case count violates frozen viability bounds")

    selected_ids = [str(case["transition_id"]) for case in selection["selected"]]
    if case_ids != selected_ids:
        raise V3LockError("materialization membership/order differs from deterministic selection")

    manifest_cases = _case_map(manifest, "id")
    packet_cases = _case_map(packet_set, "transition_id")
    adjudication_cases = _case_map(adjudications, "transition_id")
    scenario_cases = _case_map(scenarios, "transition_id")
    expected = set(case_ids)
    if not all(
        set(case_map) == expected
        for case_map in (manifest_cases, packet_cases, adjudication_cases, scenario_cases)
    ):
        raise V3LockError("case membership differs across frozen evidence inputs")

    docs_result = validate_manifest(
        documentation_snapshot_manifest_path,
        schema_path=repo / "docs/r3-documentation-snapshot-manifest.schema.json",
        expected_case_ids=case_ids,
    )
    docs_manifest, _docs_bytes = _read_json(
        documentation_snapshot_manifest_path, "documentation snapshot manifest"
    )
    doc_by_id = {str(doc["document_id"]): doc for doc in docs_manifest["documents"]}
    docs_by_case = {str(case["case_id"]): case for case in docs_manifest["cases"]}

    _validate_schema(roster, repo / "docs/r3-reviewer-roster.schema.json", "reviewer roster")
    _validate_schema(
        assignment, repo / "docs/r3-condition-assignment.schema.json", "condition assignment"
    )
    validate_balance(assignment)
    if assignment.get("source_manifest_sha256") != _sha256(manifest_bytes):
        raise V3LockError("condition assignment is not bound to the exact manifest")
    if assignment.get("participant_roster_sha256") != _sha256(roster_bytes):
        raise V3LockError("condition assignment is not bound to the exact reviewer roster")
    reviewer_protocol_path = repo / "validation/r3-benchmark/exploratory/reviewer-protocol-v1.json"
    if assignment.get("reviewer_protocol_sha256") != _sha256(reviewer_protocol_path.read_bytes()):
        raise V3LockError("condition assignment reviewer-protocol digest mismatch")
    if assignment.get("cases") != sorted(
        case_ids,
        key=lambda case_id: (
            _sha256(f"{assignment['assignment_seed']}\ncase\n{case_id}".encode()),
            case_id,
        ),
    ):
        raise V3LockError("condition assignment case ranking does not match locked cases")

    case_bindings: list[dict[str, Any]] = []
    for case in materialization_cases:
        case_id = str(case["transition_id"])
        packet_case = packet_cases[case_id]
        adjudication_case = adjudication_cases[case_id]
        scenario_case = scenario_cases[case_id]
        doc_case = docs_by_case.get(case_id)
        if not isinstance(doc_case, dict):
            raise V3LockError(f"missing documentation snapshot set for {case_id}")
        doc_ids = list(doc_case["documentation_ids"])
        selected_docs = [doc_by_id[doc_id] for doc_id in doc_ids]
        doc_set_sha = documentation_set_digest(selected_docs)
        if doc_case["documentation_snapshot_set_sha256"] != doc_set_sha:
            raise V3LockError(f"documentation snapshot-set digest mismatch for {case_id}")

        required_doc_refs = {
            f"documentation_snapshot:{doc_id}:{doc_by_id[doc_id]['snapshot_sha256']}"
            for doc_id in doc_ids
        }
        evidence_refs = set(adjudication_case.get("evidence_refs", []))
        if not required_doc_refs <= evidence_refs:
            missing = sorted(required_doc_refs - evidence_refs)
            raise V3LockError(
                "adjudication "
                f"{case_id} is not bound to every frozen documentation snapshot: {missing}"
            )

        case_bindings.append(
            {
                "case_id": case_id,
                "repository_url": case["repository_url"],
                "source_path": case["source_path"],
                "baseline_commit": case["baseline"]["source_commit"],
                "candidate_commit": case["candidate"]["source_commit"],
                "baseline_sha256": case["baseline"]["sha256"],
                "candidate_sha256": case["candidate"]["sha256"],
                "review_packet_sha256": canonical_sha256(packet_case),
                "documentation_snapshot_ids": doc_ids,
                "documentation_snapshot_set_sha256": doc_set_sha,
                "primary_scenario_sha256": _primary_scenario_sha(scenario_case),
                "reference_adjudication_sha256": canonical_sha256(adjudication_case),
            }
        )

    environment_sha = _sha256(environment_bytes)
    command_identity = {
        "product_commit": PRODUCT_COMMIT,
        "environment_lock_sha256": environment_sha,
        "interface": freeze_contract["permitdiff_execution"]["interface"],
        "scenario_present_command_argv": freeze_contract["permitdiff_execution"][
            "scenario_present_command_argv"
        ],
        "fixed_flags": freeze_contract["permitdiff_execution"]["fixed_flags"],
        "scenario_absent_behavior": freeze_contract["permitdiff_execution"][
            "scenario_absent_behavior"
        ],
    }

    lock = {
        "schema_version": LOCK_SCHEMA_VERSION,
        "protocol_version": "r3-benchmark-protocol-v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "measurement_contract_version": "r3-exploratory-measurement-contract-v2",
        "hardening_contract_version": HARDENING_CONTRACT_VERSION,
        "corpus_id": manifest["corpus_id"],
        "study_repository_commit": head,
        "product_execution_performed": False,
        "product_execution_commit": PRODUCT_COMMIT,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "case_bindings": case_bindings,
        "screened_ledger_sha256": _sha256(ledger_bytes),
        "selection_sha256": _sha256(selection_bytes),
        "manifest_sha256": _sha256(manifest_bytes),
        "materialization_sha256": _sha256(materialization_bytes),
        "review_packet_set_sha256": _sha256(packet_bytes),
        "adjudications_sha256": _sha256(adjudication_bytes),
        "scenario_channel_set_sha256": _sha256(scenario_bytes),
        "documentation_snapshot_manifest_sha256": docs_result["manifest_sha256"],
        "reviewer_roster_sha256": _sha256(roster_bytes),
        "condition_assignment_sha256": _sha256(assignment_bytes),
        "environment_lock_sha256": environment_sha,
        "product_wheel_sha256": product_wheel_sha256,
        "runtime_dependency_lock_sha256": runtime_lock["sha256"],
        "build_dependency_lock_sha256": build_lock["sha256"],
        "permitdiff_command_identity_sha256": canonical_sha256(command_identity),
        "methodology_components": methodology,
    }
    _validate_schema(lock, repo / "docs/r3-pre-execution-lock-v3.schema.json", "v3 lock")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return lock


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--repo", type=Path, default=root)
    parser.add_argument("--screened-ledger", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--materialization", type=Path, required=True)
    parser.add_argument("--review-packets", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
    parser.add_argument(
        "--measurement-contract",
        type=Path,
        default=root / "validation/r3-benchmark/exploratory/measurement-contract-v2.json",
    )
    parser.add_argument("--scenario-channels", type=Path, required=True)
    parser.add_argument("--documentation-snapshots", type=Path, required=True)
    parser.add_argument("--reviewer-roster", type=Path, required=True)
    parser.add_argument("--condition-assignment", type=Path, required=True)
    parser.add_argument(
        "--environment-lock",
        type=Path,
        default=root
        / "validation/r3-benchmark/exploratory/permitdiff-execution-environment-v1.json",
    )
    parser.add_argument(
        "--freeze-completion-contract",
        type=Path,
        default=root / "validation/r3-benchmark/exploratory/freeze-completion-contract-v1.json",
    )
    parser.add_argument("--product-wheel", type=Path, required=True)
    parser.add_argument(
        "--hardening-contract",
        type=Path,
        default=root
        / "validation/r3-benchmark/exploratory/pre-discovery-hardening-contract-v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        create_v3_lock(
            repo=args.repo,
            screened_ledger_path=args.screened_ledger,
            selection_path=args.selection,
            manifest_path=args.manifest,
            materialization_path=args.materialization,
            review_packet_set_path=args.review_packets,
            adjudications_path=args.adjudications,
            measurement_contract_path=args.measurement_contract,
            scenario_channel_set_path=args.scenario_channels,
            documentation_snapshot_manifest_path=args.documentation_snapshots,
            reviewer_roster_path=args.reviewer_roster,
            condition_assignment_path=args.condition_assignment,
            environment_lock_path=args.environment_lock,
            freeze_completion_contract_path=args.freeze_completion_contract,
            hardening_contract_path=args.hardening_contract,
            product_wheel_path=args.product_wheel,
            output_path=args.output,
        )
    except (V3LockError, PreExecutionLockError, ValueError, OSError, KeyError) as exc:
        print(f"R3 v3 pre-execution lock failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
