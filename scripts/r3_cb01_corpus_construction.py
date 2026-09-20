#!/usr/bin/env python3
"""Pure reusable CB-01 corpus-construction semantics (Packet A).

This module performs no network access, no GitHub API access, no filesystem
publication, and no PermitDiff execution. It provides pure or read-only
semantic validation and deterministic derivation for the prospective CB-01
construction chain:

raw public discovery v2 -> screening decisions v1 -> screened discovery v1
-> public selection v2 -> CB-01 construction lineage v1.

Temporary duplication with ``scripts/discover_r3_benchmark_candidates.py``
(selection-key / transition-ID formulas, exclusion vocabulary, and the
pre-exposed contamination register shape) is intentional for Packet A.
Packet B will migrate operational producers to this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

CB01_SCHEMA_VERSION = "permitdiff.dev/r3-cb01-corpus-construction-contract/v1"
CB01_CONTRACT_VERSION = "r3-cb01-corpus-construction-v1"
PLAN_VERSION = "r3-exploratory-corpus-plan-v1"
PROTOCOL_VERSION = "r3-benchmark-protocol-v1"

RAW_LEDGER_SCHEMA_VERSION = "permitdiff.dev/r3-public-discovery-ledger/v2"
SCREENING_DECISIONS_SCHEMA_VERSION = "permitdiff.dev/r3-screening-decisions/v1"
SCREENED_LEDGER_SCHEMA_VERSION = "permitdiff.dev/r3-screened-discovery-ledger/v1"
SELECTION_SCHEMA_VERSION = "permitdiff.dev/r3-public-selection/v2"
LINEAGE_SCHEMA_VERSION = "permitdiff.dev/r3-cb01-corpus-construction-lineage/v1"

CANONICAL_PUBLIC_PRODUCER_ID = "permitdiff-r3-canonical-public-discovery-v2"

TARGET_CASE_COUNT = 18
MAX_CASES_PER_REPOSITORY = 2
MINIMUM_VIABLE_SELECTED_CASE_COUNT = 12

CANDIDATE_PATHS = (".claude/settings.json", ".claude/settings.local.json")
CANDIDATE_PATH_SET = frozenset(CANDIDATE_PATHS)

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REPO_FULL_NAME_RE = re.compile(r"^[^/]+/[^/]+$")
_TRANSITION_ID_RE = re.compile(r"^gh-[0-9a-f]{20}$")
_REPO_URL_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+$")

_MAX_REVIEWER_LENGTH = 128
_MAX_RATIONALE_LENGTH = 10000

FIXED_EXCLUSION_REASONS = frozenset(
    {
        "unavailable_provenance",
        "ambiguous_parent_transition",
        "artifact_parse_failure",
        "no_authorization_relevant_change",
        "duplicate_transition",
        "insufficient_public_semantics",
        "private_or_sensitive_content",
        "non_project_or_unscoped_settings",
        "pre_exposed_engineering_control",
    }
)


class CB01ConstructionError(ValueError):
    """Base error for CB-01 construction-semantics violations."""


class CB01ContractError(CB01ConstructionError):
    """Raised when the CB-01 machine contract is invalid or unbound."""


class CB01RawLedgerError(CB01ConstructionError):
    """Raised when a raw public discovery v2 ledger is invalid."""


class CB01ScreeningError(CB01ConstructionError):
    """Raised when screening decisions or derivation are invalid."""


class CB01SelectionError(CB01ConstructionError):
    """Raised when a public selection v2 artifact is invalid."""


class CB01BelowMinimumError(CB01SelectionError):
    """Raised when SELECTED_CASE_COUNT is below the frozen minimum of 12."""


class CB01LineageError(CB01ConstructionError):
    """Raised when CB-01 lineage evidence is invalid."""


def sha256_bytes(payload: bytes) -> str:
    """Return lowercase SHA-256 for bytes."""

    return hashlib.sha256(payload).hexdigest()


def canonical_repository_url(repository_full_name: str) -> str:
    """Return the canonical public repository URL for a full name."""

    return f"https://github.com/{repository_full_name}"


def selection_key_for(
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    """Compute the frozen deterministic selection key."""

    material = f"{repository_url}\n{baseline_commit}\n{candidate_commit}\n{path}".encode()
    return sha256_bytes(material)


def transition_id_for(
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    """Return the frozen stable transition identifier."""

    return "gh-" + selection_key_for(repository_url, baseline_commit, candidate_commit, path)[:20]


def _contamination_register(contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    register = contract.get("contamination_register")
    if not isinstance(register, list) or not all(isinstance(item, Mapping) for item in register):
        raise CB01ContractError("CB-01 contract has a malformed contamination_register")
    return list(register)  # type: ignore[return-value]


def contamination_status_for(
    canonical_repository_url_value: str,
    baseline_commit: str,
    candidate_commit: str,
    path: str,
    contract: Mapping[str, Any],
) -> str:
    """Recompute contamination status from the frozen register.

    Never trust stored ``contamination_status``; the caller must compare the
    recomputed value against the stored value.
    """

    for entry in _contamination_register(contract):
        if (
            entry.get("repository_url") == canonical_repository_url_value
            and entry.get("baseline_commit") == baseline_commit
            and entry.get("candidate_commit") == candidate_commit
            and entry.get("path") == path
        ):
            return "pre_exposed_engineering_control"
    return "clean"


def _is_strict_sha1(value: Any) -> bool:
    """Return True when value is a lowercase 40-hex SHA-1."""

    return isinstance(value, str) and _SHA1_RE.match(value) is not None


def _is_strict_sha256(value: Any) -> bool:
    """Return True when value is a lowercase 64-hex SHA-256."""

    return isinstance(value, str) and _SHA256_RE.match(value) is not None


def _validate_repository_full_name(full_name: Any, transition_id: Any) -> str:
    """Require strict owner/repository form with exactly one slash."""

    if not isinstance(full_name, str) or _REPO_FULL_NAME_RE.match(full_name) is None:
        raise CB01ConstructionError(
            f"transition has an invalid repository_full_name for {transition_id}"
        )
    return full_name


def _validate_commit_sha1(value: Any, field: str, transition_id: Any) -> str:
    """Require a lowercase 40-hex commit SHA."""

    if not _is_strict_sha1(value):
        raise CB01ConstructionError(
            f"transition has an invalid {field} for {transition_id}"
        )
    assert isinstance(value, str)
    return value


def _validate_transition_path(path: Any, transition_id: Any) -> str:
    """Require a frozen candidate path."""

    if path not in CANDIDATE_PATH_SET:
        raise CB01ConstructionError(
            f"transition has an invalid path for {transition_id}"
        )
    assert isinstance(path, str)
    return path


def _validate_permissions_changed(value: Any, transition_id: Any) -> None:
    """Require permissions_changed to be bool or null (never int/str)."""

    if value is not None and not isinstance(value, bool):
        raise CB01ConstructionError(
            f"transition has an invalid permissions_changed for {transition_id}"
        )


def _validate_exclusion_list(reasons: Any, transition_id: Any) -> list[str]:
    """Require a list of preregistered unique exclusion reasons."""

    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        raise CB01ConstructionError(
            f"transition has malformed exclusion_reasons for {transition_id}"
        )
    unknown = set(reasons) - FIXED_EXCLUSION_REASONS
    if unknown:
        raise CB01ConstructionError(
            f"transition {transition_id} uses non-preregistered "
            f"exclusions: {sorted(unknown)}"
        )
    if len(set(reasons)) != len(reasons):
        raise CB01ConstructionError(
            f"transition {transition_id} has duplicate exclusion_reasons"
        )
    return list(reasons)


def _validate_manual_review_raw(transition: Mapping[str, Any]) -> None:
    """Require pending->True and resolved->False manual-review semantics."""

    status = transition.get("screening_status")
    manual = transition.get("manual_review_required")
    transition_id = transition.get("transition_id")
    if status == "pending":
        if manual is not True:
            raise CB01RawLedgerError(
                f"pending transition {transition_id} must require manual review"
            )
    elif status in {"excluded"}:
        if manual is not False:
            raise CB01RawLedgerError(
                f"resolved transition {transition_id} cannot require manual review"
            )
    else:
        # Unknown status is reported by the status check itself; still
        # require an exact boolean so truthy stand-ins cannot pass.
        if manual is not True and manual is not False:
            raise CB01RawLedgerError(
                f"transition {transition_id} has an invalid manual_review_required"
            )


def _validate_instructions(instructions: Any) -> None:
    """Require a non-empty instructions string."""

    if not isinstance(instructions, str) or not instructions.strip():
        raise CB01ScreeningError("screening decisions have invalid instructions")


def _validate_reviewer(reviewer: Any, transition_id: Any, *, required: bool) -> None:
    """Validate reviewer presence, type, and length bounds."""

    if not required:
        if reviewer is not None:
            raise CB01ScreeningError(
                f"screening decision for {transition_id} must not have a reviewer"
            )
        return
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise CB01ScreeningError(
            f"screening decision for {transition_id} requires a reviewer"
        )
    if len(reviewer) > _MAX_REVIEWER_LENGTH:
        raise CB01ScreeningError(
            f"screening decision for {transition_id} has an overlong reviewer"
        )


def _validate_rationale(rationale: Any, transition_id: Any, *, required: bool) -> None:
    """Validate rationale presence, type, and length bounds."""

    if not required:
        if rationale is not None:
            raise CB01ScreeningError(
                f"screening decision for {transition_id} must not have a rationale"
            )
        return
    if not isinstance(rationale, str) or not rationale.strip():
        raise CB01ScreeningError(
            f"screening decision for {transition_id} requires a rationale"
        )
    if len(rationale) > _MAX_RATIONALE_LENGTH:
        raise CB01ScreeningError(
            f"screening decision for {transition_id} has an overlong rationale"
        )


def _check_contract_versions(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != CB01_SCHEMA_VERSION:
        raise CB01ContractError("unsupported CB-01 contract schema version")
    if contract.get("contract_version") != CB01_CONTRACT_VERSION:
        raise CB01ContractError("unsupported CB-01 contract version")
    if contract.get("plan_version") != PLAN_VERSION:
        raise CB01ContractError("CB-01 contract plan version mismatch")
    if contract.get("protocol_version") != PROTOCOL_VERSION:
        raise CB01ContractError("CB-01 contract protocol version mismatch")
    if contract.get("target_case_count") != TARGET_CASE_COUNT:
        raise CB01ContractError("CB-01 contract target must remain exactly 18")
    if contract.get("maximum_cases_per_repository") != MAX_CASES_PER_REPOSITORY:
        raise CB01ContractError("CB-01 contract per-repository cap must remain exactly 2")
    if contract.get("minimum_viable_selected_case_count") != MINIMUM_VIABLE_SELECTED_CASE_COUNT:
        raise CB01ContractError("CB-01 contract minimum must remain exactly 12")
    artifacts = contract.get("artifact_versions")
    if not isinstance(artifacts, Mapping):
        raise CB01ContractError("CB-01 contract is missing artifact_versions")
    expected = {
        "raw_public_discovery_ledger": RAW_LEDGER_SCHEMA_VERSION,
        "screening_decisions": SCREENING_DECISIONS_SCHEMA_VERSION,
        "screened_discovery_ledger": SCREENED_LEDGER_SCHEMA_VERSION,
        "public_selection": SELECTION_SCHEMA_VERSION,
        "cb01_construction_lineage": LINEAGE_SCHEMA_VERSION,
        "public_materialization": "permitdiff.dev/r3-public-materialization/v2",
    }
    for key, value in expected.items():
        if artifacts.get(key) != value:
            raise CB01ContractError(f"CB-01 contract artifact version mismatch for {key}")
    if contract.get("canonical_public_producer_id") != CANONICAL_PUBLIC_PRODUCER_ID:
        raise CB01ContractError("CB-01 contract canonical producer mismatch")


def validate_contract_binding(
    contract: Mapping[str, Any], contract_bytes: bytes
) -> Mapping[str, Any]:
    """Validate a contract object against its exact source bytes."""

    try:
        parsed = json.loads(contract_bytes)
    except json.JSONDecodeError as exc:
        raise CB01ContractError(f"CB-01 contract bytes are not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CB01ContractError("CB-01 contract bytes must contain a JSON object")
    if parsed != dict(contract):
        raise CB01ContractError("CB-01 contract object does not match exact contract bytes")
    _check_contract_versions(contract)
    return contract


def _expected_contract_digest(contract_bytes: bytes) -> str:
    return sha256_bytes(contract_bytes)


def _require_contract_digest(
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_bytes: bytes,
    *,
    context: str,
) -> None:
    validate_contract_binding(contract, contract_bytes)
    if payload.get("cb01_contract_version") != CB01_CONTRACT_VERSION:
        raise CB01ConstructionError(f"{context} cb01_contract_version mismatch")
    if payload.get("cb01_contract_sha256") != _expected_contract_digest(contract_bytes):
        raise CB01ConstructionError(f"{context} cb01_contract_sha256 does not match exact bytes")


def validate_query_frame(queries: Any, contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Validate the exact ordered ten-query frame against the contract."""

    frame = contract.get("search_frame")
    if not isinstance(frame, list) or len(frame) != 10:
        raise CB01ContractError("CB-01 contract search_frame must contain exactly ten entries")
    if not isinstance(queries, list) or len(queries) != 10:
        raise CB01RawLedgerError("raw ledger must contain exactly ten ordered query entries")
    for index, (actual, expected) in enumerate(zip(queries, frame, strict=True)):
        if not isinstance(actual, Mapping) or not isinstance(expected, Mapping):
            raise CB01RawLedgerError(f"query entry {index} must be an object")
        for field in ("query_id", "concept", "candidate_path", "api_query"):
            if actual.get(field) != expected.get(field):
                raise CB01RawLedgerError(
                    f"query entry {index} field {field!r} does not match the frozen frame"
                )
    pairs = [(str(item["query_id"]), str(item["candidate_path"])) for item in frame]  # type: ignore[index]
    if len(set(pairs)) != 10:
        raise CB01ContractError("CB-01 contract search_frame has duplicate query/path pairs")
    actual_pairs = [
        (str(item.get("query_id")), str(item.get("candidate_path")))  # type: ignore[union-attr]
        for item in queries  # type: ignore[union-attr]
    ]
    if len(set(actual_pairs)) != 10:
        raise CB01RawLedgerError("raw ledger query frame has duplicate query/path pairs")
    return list(queries)  # type: ignore[return-value]


def validate_transition_identity(
    transition: Mapping[str, Any], contract: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Recompute and require exact canonical transition identity."""

    transition_id = transition.get("transition_id")
    full_name = _validate_repository_full_name(
        transition.get("repository_full_name"), transition_id
    )
    repository_url = transition.get("repository_url")
    baseline = _validate_commit_sha1(
        transition.get("baseline_commit"), "baseline_commit", transition_id
    )
    candidate = _validate_commit_sha1(
        transition.get("candidate_commit"), "candidate_commit", transition_id
    )
    path = _validate_transition_path(transition.get("path"), transition_id)
    if not isinstance(repository_url, str) or _REPO_URL_RE.match(repository_url) is None:
        raise CB01ConstructionError(
            f"repository_url/full-name mismatch for {transition.get('transition_id')}"
        )
    expected_url = canonical_repository_url(full_name)
    if repository_url != expected_url:
        raise CB01ConstructionError(
            f"repository_url/full-name mismatch for {transition.get('transition_id')}"
        )
    _validate_permissions_changed(transition.get("permissions_changed"), transition_id)
    expected_key = selection_key_for(str(repository_url), baseline, candidate, path)
    if transition.get("selection_key") != expected_key:
        raise CB01ConstructionError(f"selection_key mismatch for {transition.get('transition_id')}")
    expected_id = transition_id_for(str(repository_url), baseline, candidate, path)
    if transition.get("transition_id") != expected_id:
        raise CB01ConstructionError(f"transition_id mismatch for {expected_id}")
    expected_contamination = contamination_status_for(
        str(repository_url), baseline, candidate, path, contract
    )
    if transition.get("contamination_status") != expected_contamination:
        raise CB01ConstructionError(
            f"contamination_status mismatch for {transition.get('transition_id')}"
        )
    return transition


def _validate_discovery_markers(transition: Mapping[str, Any]) -> None:
    markers = transition.get("discovered_by")
    if not isinstance(markers, list):
        raise CB01RawLedgerError(
            f"transition {transition.get('transition_id')} has malformed discovered_by"
        )
    for marker in markers:
        if not isinstance(marker, Mapping):
            raise CB01RawLedgerError("discovery marker must be an object")
        if marker.get("query_id") not in {"q1", "q2", "q3", "q4", "q5"}:
            raise CB01RawLedgerError("discovery marker has an invalid query_id")
        if marker.get("candidate_path") not in set(CANDIDATE_PATHS):
            raise CB01RawLedgerError("discovery marker has an invalid candidate_path")
        if set(marker.keys()) != {"query_id", "candidate_path"}:
            raise CB01RawLedgerError("discovery marker has unexpected properties")


def _check_duplicates(transitions: list[Mapping[str, Any]], *, context: str) -> None:
    identities: set[tuple[str, str, str, str]] = set()
    keys: set[str] = set()
    ids: set[str] = set()
    error = (
        CB01RawLedgerError
        if context == "raw"
        else CB01ScreeningError
        if context == "screened-derivation"
        else CB01ConstructionError
    )
    for item in transitions:
        identity = (
            str(item.get("repository_url")),
            str(item.get("baseline_commit")),
            str(item.get("candidate_commit")),
            str(item.get("path")),
        )
        key = str(item.get("selection_key"))
        transition_id = str(item.get("transition_id"))
        if identity in identities:
            raise error(f"duplicate immutable transition identity for {transition_id}")
        if key in keys:
            raise error(f"duplicate selection_key for {transition_id}")
        if transition_id in ids:
            raise error(f"duplicate transition_id for {transition_id}")
        identities.add(identity)
        keys.add(key)
        ids.add(transition_id)


def validate_raw_ledger(
    raw: Mapping[str, Any],
    raw_bytes: bytes,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> Mapping[str, Any]:
    """Validate a raw public discovery v2 ledger against exact bytes and contract."""

    try:
        parsed = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise CB01RawLedgerError(f"raw ledger bytes are not valid JSON: {exc}") from exc
    if parsed != dict(raw):
        raise CB01RawLedgerError("raw ledger object does not match exact raw bytes")
    if raw.get("schema_version") != RAW_LEDGER_SCHEMA_VERSION:
        raise CB01RawLedgerError("unsupported raw discovery ledger schema version")
    if raw.get("plan_version") != PLAN_VERSION:
        raise CB01RawLedgerError("raw ledger plan version mismatch")
    if raw.get("protocol_version") != PROTOCOL_VERSION:
        raise CB01RawLedgerError("raw ledger protocol version mismatch")
    _require_contract_digest(raw, contract, contract_bytes, context="raw ledger")
    study_commit = raw.get("study_repository_commit")
    if not _is_strict_sha1(study_commit):
        raise CB01RawLedgerError("raw ledger has an invalid study_repository_commit")
    if raw.get("producer_id") != CANONICAL_PUBLIC_PRODUCER_ID:
        raise CB01RawLedgerError("raw ledger producer_id is not the canonical public producer")
    validate_query_frame(raw.get("queries"), contract)
    transitions = raw.get("transitions")
    if not isinstance(transitions, list) or not all(
        isinstance(item, Mapping) for item in transitions
    ):
        raise CB01RawLedgerError("raw ledger transitions must be a list of objects")
    typed: list[Mapping[str, Any]] = list(transitions)  # type: ignore[arg-type]
    if raw.get("transition_count") != len(typed):
        raise CB01RawLedgerError("raw ledger transition_count does not match transitions")
    for item in typed:
        if item.get("screening_status") == "eligible":
            raise CB01RawLedgerError(
                f"raw transition {item.get('transition_id')} must not use eligible status"
            )
        if item.get("screening_status") not in {"pending", "excluded"}:
            raise CB01RawLedgerError(
                f"raw transition {item.get('transition_id')} has an unsupported status"
            )
        _validate_manual_review_raw(item)
        try:
            _validate_exclusion_list(
                item.get("exclusion_reasons"), item.get("transition_id")
            )
        except CB01ConstructionError as exc:
            raise CB01RawLedgerError(str(exc)) from exc
        try:
            validate_transition_identity(item, contract)
        except CB01ConstructionError as exc:
            # Preserve specific identity messages while reporting raw context.
            raise CB01RawLedgerError(str(exc)) from exc
        _validate_discovery_markers(item)
    _check_duplicates(typed, context="raw")
    return raw


def _validate_screening_decision_entry(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate one screening decision against the frozen v1 vocabulary."""

    transition_id = entry.get("transition_id")
    if not isinstance(transition_id, str) or _TRANSITION_ID_RE.match(transition_id) is None:
        raise CB01ScreeningError(
            f"screening decision has an invalid transition_id for {transition_id}"
        )
    repository_url = entry.get("repository_url")
    if not isinstance(repository_url, str) or _REPO_URL_RE.match(repository_url) is None:
        raise CB01ScreeningError(
            f"screening decision has an invalid repository_url for {transition_id}"
        )
    if entry.get("path") not in CANDIDATE_PATH_SET:
        raise CB01ScreeningError(
            f"screening decision has an invalid path for {transition_id}"
        )
    if not _is_strict_sha1(entry.get("baseline_commit")):
        raise CB01ScreeningError(
            f"screening decision has an invalid baseline_commit for {transition_id}"
        )
    if not _is_strict_sha1(entry.get("candidate_commit")):
        raise CB01ScreeningError(
            f"screening decision has an invalid candidate_commit for {transition_id}"
        )
    try:
        _validate_permissions_changed(entry.get("permissions_changed"), transition_id)
    except CB01ConstructionError as exc:
        raise CB01ScreeningError(str(exc)) from exc
    if entry.get("contamination_status") not in {"clean", "pre_exposed_engineering_control"}:
        raise CB01ScreeningError(
            f"screening decision has an invalid contamination_status for {transition_id}"
        )
    outcome = entry.get("decision")
    if outcome not in {"pending", "eligible", "excluded"}:
        raise CB01ScreeningError(
            f"invalid screening decision for {transition_id}: {outcome!r}"
        )
    reasons = entry.get("exclusion_reasons")
    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        raise CB01ScreeningError(
            f"screening decision has malformed exclusion_reasons for {transition_id}"
        )
    unknown = set(reasons) - FIXED_EXCLUSION_REASONS
    if unknown:
        raise CB01ScreeningError(
            f"transition {transition_id} uses non-preregistered "
            f"exclusions: {sorted(unknown)}"
        )
    if len(set(reasons)) != len(reasons):
        raise CB01ScreeningError(
            f"transition {transition_id} has duplicate exclusion_reasons"
        )
    if outcome == "pending":
        if reasons:
            raise CB01ScreeningError(
                f"pending decision for {transition_id} cannot have exclusion_reasons"
            )
        _validate_reviewer(entry.get("reviewer"), transition_id, required=False)
        _validate_rationale(entry.get("rationale"), transition_id, required=False)
    elif outcome == "eligible":
        if reasons:
            raise CB01ScreeningError(
                f"eligible decision for {transition_id} cannot have exclusion_reasons"
            )
        _validate_reviewer(entry.get("reviewer"), transition_id, required=True)
        _validate_rationale(entry.get("rationale"), transition_id, required=True)
    else:  # excluded
        if not reasons:
            raise CB01ScreeningError(
                f"excluded decision for {transition_id} requires an exclusion reason"
            )
        _validate_reviewer(entry.get("reviewer"), transition_id, required=True)
        _validate_rationale(entry.get("rationale"), transition_id, required=True)
    return entry


def _validate_decisions_object(
    decisions: Mapping[str, Any],
    decisions_bytes: bytes,
    raw_bytes: bytes,
) -> list[Mapping[str, Any]]:
    try:
        parsed = json.loads(decisions_bytes)
    except json.JSONDecodeError as exc:
        raise CB01ScreeningError(f"screening decisions bytes are not valid JSON: {exc}") from exc
    if parsed != dict(decisions):
        raise CB01ScreeningError("screening decisions object does not match exact bytes")
    if decisions.get("schema_version") != SCREENING_DECISIONS_SCHEMA_VERSION:
        raise CB01ScreeningError("unsupported screening decisions schema version")
    if decisions.get("plan_version") != PLAN_VERSION:
        raise CB01ScreeningError("screening decisions plan version mismatch")
    if decisions.get("protocol_version") != PROTOCOL_VERSION:
        raise CB01ScreeningError("screening decisions protocol version mismatch")
    if decisions.get("source_ledger_sha256") != sha256_bytes(raw_bytes):
        raise CB01ScreeningError("screening decisions are not bound to the supplied raw bytes")
    if not _is_strict_sha256(decisions.get("source_ledger_sha256")):
        raise CB01ScreeningError("screening decisions have an invalid source_ledger_sha256")
    _validate_instructions(decisions.get("instructions"))
    raw_decisions = decisions.get("decisions")
    if not isinstance(raw_decisions, list) or not all(
        isinstance(item, Mapping) for item in raw_decisions
    ):
        raise CB01ScreeningError("screening decisions must be a list of objects")
    typed: list[Mapping[str, Any]] = list(raw_decisions)  # type: ignore[arg-type]
    for entry in typed:
        _validate_screening_decision_entry(entry)
    return list(typed)


def derive_screened_ledger(
    raw: Mapping[str, Any],
    raw_bytes: bytes,
    decisions: Mapping[str, Any],
    decisions_bytes: bytes,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> dict[str, Any]:
    """Deterministically derive the screened discovery v1 ledger."""

    validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)
    if raw.get("discovery_complete") is not True:
        raise CB01ScreeningError("screening requires a complete raw discovery ledger")
    entries = _validate_decisions_object(decisions, decisions_bytes, raw_bytes)

    pending: dict[str, Mapping[str, Any]] = {}
    for item in raw["transitions"]:  # type: ignore[union-attr]
        assert isinstance(item, Mapping)
        if item.get("screening_status") == "pending":
            pending[str(item["transition_id"])] = item

    by_id: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        transition_id = entry.get("transition_id")
        if not isinstance(transition_id, str):
            raise CB01ScreeningError("screening decision has an invalid transition_id")
        if transition_id in by_id:
            raise CB01ScreeningError(f"duplicate screening decision for {transition_id}")
        by_id[transition_id] = entry

    missing = sorted(set(pending) - set(by_id))
    extra = sorted(set(by_id) - set(pending))
    if missing:
        raise CB01ScreeningError(f"screening decisions are missing pending transitions: {missing}")
    if extra:
        raise CB01ScreeningError(f"screening decisions contain non-pending transitions: {extra}")

    screened_transitions: list[dict[str, Any]] = []
    for item in raw["transitions"]:  # type: ignore[union-attr]
        assert isinstance(item, Mapping)
        target = copy.deepcopy(dict(item))
        transition_id = str(item["transition_id"])
        if transition_id not in pending:
            if target.get("screening_status") not in {"excluded"}:
                raise CB01ScreeningError(
                    f"non-pending raw transition has invalid status: {transition_id}"
                )
            target["manual_review_required"] = False
            screened_transitions.append(target)
            continue
        source = pending[transition_id]
        decision = by_id[transition_id]
        for field in (
            "transition_id",
            "repository_url",
            "path",
            "baseline_commit",
            "candidate_commit",
            "permissions_changed",
            "contamination_status",
        ):
            if source.get(field) != decision.get(field):
                raise CB01ScreeningError(
                    f"screening decision metadata mismatch for {transition_id}"
                )
        outcome = decision.get("decision")
        if outcome == "pending":
            raise CB01ScreeningError(f"screening decision remains pending for {transition_id}")
        if outcome not in {"eligible", "excluded"}:
            raise CB01ScreeningError(f"invalid screening decision for {transition_id}: {outcome!r}")
        if outcome == "eligible":
            if decision.get("exclusion_reasons"):
                raise CB01ScreeningError(
                    f"eligible decision for {transition_id} cannot have exclusion_reasons"
                )
            recomputed = contamination_status_for(
                str(source.get("repository_url")),
                str(source.get("baseline_commit")),
                str(source.get("candidate_commit")),
                str(source.get("path")),
                contract,
            )
            if recomputed != "clean":
                raise CB01ScreeningError(
                    f"contaminated transition cannot be eligible: {transition_id}"
                )
            if source.get("contamination_status") != "clean":
                raise CB01ScreeningError(
                    f"contaminated transition cannot be eligible: {transition_id}"
                )
            for field in ("baseline_blob", "candidate_blob", "baseline_sha256", "candidate_sha256"):
                if source.get(field) is None:
                    raise CB01ScreeningError(
                        f"eligible transition lacks immutable artifact provenance: {transition_id}"
                    )
            target["screening_status"] = "eligible"
            target["exclusion_reasons"] = []
        else:
            reasons = decision.get("exclusion_reasons")
            if not isinstance(reasons, list) or not reasons:
                raise CB01ScreeningError(
                    f"excluded transition requires an exclusion reason: {transition_id}"
                )
            unknown = {str(reason) for reason in reasons} - FIXED_EXCLUSION_REASONS
            if unknown:
                raise CB01ScreeningError(
                    f"transition {transition_id} uses non-preregistered "
                    f"exclusions: {sorted(unknown)}"
                )
            if len(set(str(reason) for reason in reasons)) != len(reasons):
                raise CB01ScreeningError(
                    f"transition {transition_id} has duplicate exclusion_reasons"
                )
            target["screening_status"] = "excluded"
            target["exclusion_reasons"] = sorted({str(reason) for reason in reasons})
        target["manual_review_required"] = False
        screened_transitions.append(target)

    if any(item.get("screening_status") == "pending" for item in screened_transitions):
        raise CB01ScreeningError("screened ledger still contains pending transitions")

    screened_transitions.sort(key=lambda item: str(item["selection_key"]))
    for item in screened_transitions:
        validate_transition_identity(item, contract)
        if item.get("screening_status") not in {"eligible", "excluded"}:
            raise CB01ScreeningError("screened ledger has an unsupported status")
        if item.get("manual_review_required") is not False:
            raise CB01ScreeningError("screened ledger must not require manual review")
        if item.get("screening_status") == "eligible" and item.get("exclusion_reasons"):
            raise CB01ScreeningError("eligible screened transition cannot have exclusions")
    _check_duplicates(screened_transitions, context="screened-derivation")

    return {
        "schema_version": SCREENED_LEDGER_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "cb01_contract_version": CB01_CONTRACT_VERSION,
        "cb01_contract_sha256": sha256_bytes(contract_bytes),
        "study_repository_commit": raw["study_repository_commit"],
        "source_discovery_ledger_sha256": sha256_bytes(raw_bytes),
        "source_screening_decisions_sha256": sha256_bytes(decisions_bytes),
        "transition_count": len(screened_transitions),
        "transitions": screened_transitions,
    }


def validate_screened_ledger(
    screened: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> Mapping[str, Any]:
    """Validate a screened discovery v1 ledger (without parent bytes)."""

    if screened.get("schema_version") != SCREENED_LEDGER_SCHEMA_VERSION:
        raise CB01ScreeningError("unsupported screened ledger schema version")
    if screened.get("plan_version") != PLAN_VERSION:
        raise CB01ScreeningError("screened ledger plan version mismatch")
    if screened.get("protocol_version") != PROTOCOL_VERSION:
        raise CB01ScreeningError("screened ledger protocol version mismatch")
    _require_contract_digest(screened, contract, contract_bytes, context="screened ledger")
    if "generated_at" in screened:
        raise CB01ScreeningError("screened ledger must not contain generated_at")
    study_commit = screened.get("study_repository_commit")
    if not _is_strict_sha1(study_commit):
        raise CB01ScreeningError("screened ledger has an invalid study_repository_commit")
    transitions = screened.get("transitions")
    if not isinstance(transitions, list) or not all(
        isinstance(item, Mapping) for item in transitions
    ):
        raise CB01ScreeningError("screened ledger transitions must be a list of objects")
    typed: list[Mapping[str, Any]] = list(transitions)  # type: ignore[arg-type]
    if screened.get("transition_count") != len(typed):
        raise CB01ScreeningError("screened ledger transition_count does not match transitions")
    for item in typed:
        if item.get("screening_status") not in {"eligible", "excluded"}:
            raise CB01ScreeningError("screened ledger must never contain pending status")
        if item.get("manual_review_required") is not False:
            raise CB01ScreeningError("screened ledger must not require manual review")
        reasons = item.get("exclusion_reasons")
        if not isinstance(reasons, list) or not all(
            isinstance(reason, str) for reason in reasons
        ):
            raise CB01ScreeningError("screened ledger has malformed exclusion reasons")
        unknown = set(reasons) - FIXED_EXCLUSION_REASONS
        if unknown:
            raise CB01ScreeningError(f"screened ledger uses unknown exclusions: {sorted(unknown)}")
        if len(set(reasons)) != len(reasons):
            raise CB01ScreeningError(
                f"screened transition {item.get('transition_id')} has duplicate exclusion_reasons"
            )
        if item.get("screening_status") == "eligible":
            if reasons:
                raise CB01ScreeningError("eligible screened transition cannot have exclusions")
            if item.get("contamination_status") != "clean":
                raise CB01ScreeningError("eligible screened transition cannot be contaminated")
            for field in ("baseline_blob", "candidate_blob", "baseline_sha256", "candidate_sha256"):
                if item.get(field) is None:
                    raise CB01ScreeningError("eligible screened transition lacks provenance")
        try:
            validate_transition_identity(item, contract)
        except CB01ConstructionError as exc:
            raise CB01ScreeningError(str(exc)) from exc
    _check_duplicates(typed, context="screened")
    return screened


def derive_counts(screened: Mapping[str, Any]) -> dict[str, Any]:
    """Derive RAW_ELIGIBLE_COUNT, CAP_SEQUENCE, SELECTED, and SHORTFALL."""

    transitions = screened.get("transitions")
    if not isinstance(transitions, list):
        raise CB01SelectionError("screened ledger transitions must be a list")
    eligible = [
        item
        for item in transitions
        if isinstance(item, Mapping) and item.get("screening_status") == "eligible"
    ]
    raw_eligible_count = len(eligible)
    ordered = sorted(eligible, key=lambda item: str(item["selection_key"]))  # type: ignore[union-attr]
    cap_sequence: list[Mapping[str, Any]] = []
    repo_counts: dict[str, int] = defaultdict(int)
    for item in ordered:
        repository = str(item["repository_full_name"])  # type: ignore[union-attr]
        if repo_counts[repository] >= MAX_CASES_PER_REPOSITORY:
            continue
        cap_sequence.append(item)
        repo_counts[repository] += 1
    cap_admissible_count = len(cap_sequence)
    selected = cap_sequence[:TARGET_CASE_COUNT]
    selected_case_count = len(selected)
    shortfall = TARGET_CASE_COUNT - selected_case_count
    return {
        "raw_eligible_count": raw_eligible_count,
        "cap_admissible_count": cap_admissible_count,
        "cap_sequence": cap_sequence,
        "selected": selected,
        "selected_case_count": selected_case_count,
        "shortfall": shortfall,
    }


def derive_selection_v2(
    screened: Mapping[str, Any],
    screened_bytes: bytes,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> dict[str, Any]:
    """Deterministically derive the public selection v2 payload."""

    try:
        parsed = json.loads(screened_bytes)
    except json.JSONDecodeError as exc:
        raise CB01SelectionError(f"screened bytes are not valid JSON: {exc}") from exc
    if parsed != dict(screened):
        raise CB01SelectionError("screened object does not match exact screened bytes")
    validate_screened_ledger(screened, contract, contract_bytes)
    counts = derive_counts(screened)
    if counts["selected_case_count"] < MINIMUM_VIABLE_SELECTED_CASE_COUNT:
        raise CB01BelowMinimumError(
            f"cap-admissible selected pool {counts['selected_case_count']} is below frozen "
            f"minimum {MINIMUM_VIABLE_SELECTED_CASE_COUNT}; refuse to finalize selection"
        )
    selected_cases: list[dict[str, Any]] = []
    for rank, item in enumerate(counts["selected"], start=1):
        assert isinstance(item, Mapping)
        selected_cases.append(
            {
                "rank": rank,
                "transition_id": item["transition_id"],
                "repository_full_name": item["repository_full_name"],
                "repository_url": item["repository_url"],
                "path": item["path"],
                "baseline_commit": item["baseline_commit"],
                "candidate_commit": item["candidate_commit"],
                "baseline_blob": item["baseline_blob"],
                "candidate_blob": item["candidate_blob"],
                "baseline_sha256": item["baseline_sha256"],
                "candidate_sha256": item["candidate_sha256"],
                "selection_key": item["selection_key"],
            }
        )
    return {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "cb01_contract_version": CB01_CONTRACT_VERSION,
        "cb01_contract_sha256": sha256_bytes(contract_bytes),
        "study_repository_commit": screened["study_repository_commit"],
        "source_screened_ledger_sha256": sha256_bytes(screened_bytes),
        "target_case_count": TARGET_CASE_COUNT,
        "maximum_cases_per_repository": MAX_CASES_PER_REPOSITORY,
        "minimum_viable_case_count": MINIMUM_VIABLE_SELECTED_CASE_COUNT,
        "raw_eligible_count": counts["raw_eligible_count"],
        "cap_admissible_count": counts["cap_admissible_count"],
        "selected_case_count": counts["selected_case_count"],
        "shortfall": counts["shortfall"],
        "selected": selected_cases,
    }


def validate_selection_v2(
    selection: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> Mapping[str, Any]:
    """Validate selection-v2 shape, constants, and deterministic invariants."""

    if selection.get("schema_version") != SELECTION_SCHEMA_VERSION:
        raise CB01SelectionError("unsupported public selection schema version")
    if selection.get("plan_version") != PLAN_VERSION:
        raise CB01SelectionError("selection plan version mismatch")
    if selection.get("protocol_version") != PROTOCOL_VERSION:
        raise CB01SelectionError("selection protocol version mismatch")
    _require_contract_digest(selection, contract, contract_bytes, context="selection")
    if "generated_at" in selection:
        raise CB01SelectionError("selection must not contain generated_at")
    if "eligible_case_count" in selection:
        raise CB01SelectionError("selection must not contain legacy eligible_case_count")
    if selection.get("target_case_count") != TARGET_CASE_COUNT:
        raise CB01SelectionError("selection target must remain exactly 18")
    if selection.get("maximum_cases_per_repository") != MAX_CASES_PER_REPOSITORY:
        raise CB01SelectionError("selection per-repository cap must remain exactly 2")
    if selection.get("minimum_viable_case_count") != MINIMUM_VIABLE_SELECTED_CASE_COUNT:
        raise CB01SelectionError("selection minimum must remain exactly 12")
    selected = selection.get("selected")
    if not isinstance(selected, list) or not all(isinstance(item, Mapping) for item in selected):
        raise CB01SelectionError("selection selected field must contain only objects")
    typed: list[Mapping[str, Any]] = list(selected)  # type: ignore[arg-type]
    if selection.get("selected_case_count") != len(typed):
        raise CB01SelectionError("selected_case_count does not match selected cases")
    if selection.get("shortfall") != TARGET_CASE_COUNT - len(typed):
        raise CB01SelectionError("selection shortfall does not match target and selected count")
    if len(typed) > TARGET_CASE_COUNT:
        raise CB01SelectionError("selection exceeds frozen target")
    if len(typed) < MINIMUM_VIABLE_SELECTED_CASE_COUNT:
        raise CB01BelowMinimumError("selection is below the frozen 12-case minimum")
    expected_ranks = list(range(1, len(typed) + 1))
    if [item.get("rank") for item in typed] != expected_ranks:
        raise CB01SelectionError("selected case ranks must be contiguous and ordered")
    keys = [str(item.get("selection_key")) for item in typed]
    if keys != sorted(keys):
        raise CB01SelectionError("selected cases must follow selection_key ascending order")
    seen: set[str] = set()
    repo_counts: dict[str, int] = defaultdict(int)
    for item in typed:
        transition_id = item.get("transition_id")
        if not isinstance(transition_id, str) or _TRANSITION_ID_RE.match(transition_id) is None:
            raise CB01SelectionError(
                f"selected case has an invalid transition_id for {transition_id}"
            )
        if transition_id in seen:
            raise CB01SelectionError(f"duplicate selected transition_id: {transition_id}")
        seen.add(transition_id)
        try:
            repository = _validate_repository_full_name(
                item.get("repository_full_name"), transition_id
            )
        except CB01ConstructionError as exc:
            raise CB01SelectionError(str(exc)) from exc
        repo_counts[repository] += 1
        if repo_counts[repository] > MAX_CASES_PER_REPOSITORY:
            raise CB01SelectionError(f"repository case cap exceeded for {repository}")
        repository_url = item.get("repository_url")
        if not isinstance(repository_url, str) or _REPO_URL_RE.match(repository_url) is None:
            raise CB01SelectionError(
                f"repository_url/full-name mismatch for {transition_id}"
            )
        expected_url = canonical_repository_url(repository)
        if repository_url != expected_url:
            raise CB01SelectionError(f"repository_url/full-name mismatch for {transition_id}")
        try:
            _validate_commit_sha1(
                item.get("baseline_commit"), "baseline_commit", transition_id
            )
            _validate_commit_sha1(
                item.get("candidate_commit"), "candidate_commit", transition_id
            )
            _validate_transition_path(item.get("path"), transition_id)
        except CB01ConstructionError as exc:
            raise CB01SelectionError(str(exc)) from exc
        if not _is_strict_sha1(item.get("baseline_blob")):
            raise CB01SelectionError(
                f"selected case has an invalid baseline_blob for {transition_id}"
            )
        if not _is_strict_sha1(item.get("candidate_blob")):
            raise CB01SelectionError(
                f"selected case has an invalid candidate_blob for {transition_id}"
            )
        if not _is_strict_sha256(item.get("baseline_sha256")):
            raise CB01SelectionError(
                f"selected case has an invalid baseline_sha256 for {transition_id}"
            )
        if not _is_strict_sha256(item.get("candidate_sha256")):
            raise CB01SelectionError(
                f"selected case has an invalid candidate_sha256 for {transition_id}"
            )
        expected_key = selection_key_for(
            str(item.get("repository_url")),
            str(item.get("baseline_commit")),
            str(item.get("candidate_commit")),
            str(item.get("path")),
        )
        if item.get("selection_key") != expected_key:
            raise CB01SelectionError(f"selection key mismatch for {transition_id}")
        if item.get("transition_id") != "gh-" + expected_key[:20]:
            raise CB01SelectionError(f"transition_id mismatch for {transition_id}")
    return selection


def derive_lineage_v1(
    raw: Mapping[str, Any],
    raw_bytes: bytes,
    decisions: Mapping[str, Any],
    decisions_bytes: bytes,
    screened: Mapping[str, Any],
    screened_bytes: bytes,
    selection: Mapping[str, Any],
    selection_bytes: bytes,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> dict[str, Any]:
    """Derive the expected CB-01 construction-lineage v1 payload."""

    validate_contract_binding(contract, contract_bytes)
    validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)
    try:
        if json.loads(decisions_bytes) != dict(decisions):
            raise CB01LineageError("decisions object does not match exact decisions bytes")
    except json.JSONDecodeError as exc:
        raise CB01LineageError(f"decisions bytes are not valid JSON: {exc}") from exc
    try:
        if json.loads(screened_bytes) != dict(screened):
            raise CB01LineageError("screened object does not match exact screened bytes")
    except json.JSONDecodeError as exc:
        raise CB01LineageError(f"screened bytes are not valid JSON: {exc}") from exc
    try:
        if json.loads(selection_bytes) != dict(selection):
            raise CB01LineageError("selection object does not match exact selection bytes")
    except json.JSONDecodeError as exc:
        raise CB01LineageError(f"selection bytes are not valid JSON: {exc}") from exc

    expected_screened = derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    if expected_screened != dict(screened):
        raise CB01LineageError(
            "screened ledger differs from deterministic raw+decisions derivation"
        )
    expected_selection = derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    if expected_selection != dict(selection):
        raise CB01LineageError("selection differs from deterministic screened derivation")

    study_commit = raw.get("study_repository_commit")
    for label, payload in (("screened", screened), ("selection", selection)):
        if payload.get("study_repository_commit") != study_commit:
            raise CB01LineageError(f"{label} study_repository_commit does not match raw ledger")
    if screened.get("source_discovery_ledger_sha256") != sha256_bytes(raw_bytes):
        raise CB01LineageError("screened source_discovery_ledger_sha256 mismatch")
    if screened.get("source_screening_decisions_sha256") != sha256_bytes(decisions_bytes):
        raise CB01LineageError("screened source_screening_decisions_sha256 mismatch")
    if selection.get("source_screened_ledger_sha256") != sha256_bytes(screened_bytes):
        raise CB01LineageError("selection source_screened_ledger_sha256 mismatch")

    counts = derive_counts(screened)
    if (
        selection.get("raw_eligible_count") != counts["raw_eligible_count"]
        or selection.get("cap_admissible_count") != counts["cap_admissible_count"]
        or selection.get("selected_case_count") != counts["selected_case_count"]
    ):
        raise CB01LineageError("selection counts do not match screened derivation")

    return {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "cb01_contract_version": CB01_CONTRACT_VERSION,
        "cb01_contract_sha256": sha256_bytes(contract_bytes),
        "study_repository_commit": study_commit,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "raw_discovery_ledger_sha256": sha256_bytes(raw_bytes),
        "screening_decisions_sha256": sha256_bytes(decisions_bytes),
        "screened_discovery_ledger_sha256": sha256_bytes(screened_bytes),
        "public_selection_sha256": sha256_bytes(selection_bytes),
        "raw_eligible_count": counts["raw_eligible_count"],
        "cap_admissible_count": counts["cap_admissible_count"],
        "selected_case_count": counts["selected_case_count"],
        "target_case_count": TARGET_CASE_COUNT,
        "maximum_cases_per_repository": MAX_CASES_PER_REPOSITORY,
        "minimum_viable_case_count": MINIMUM_VIABLE_SELECTED_CASE_COUNT,
        "shortfall": counts["shortfall"],
    }
