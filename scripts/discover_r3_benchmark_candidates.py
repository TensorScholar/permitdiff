#!/usr/bin/env python3
"""Discover and deterministically select R3 public historical benchmark candidates.

This script implements the preregistered discovery mechanics only. It never imports or
executes PermitDiff analysis code. Live discovery uses GitHub's public REST API and may
require a GitHub token because GitHub code search is authenticated/rate-limited.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import IncompleteRead, RemoteDisconnected
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from scripts import r3_cb01_corpus_construction as _cb01
from scripts.r3_pre_discovery_contract import (
    MAX_CASES_PER_REPOSITORY,
    TARGET_CASES,
)

PLAN_VERSION = "r3-exploratory-corpus-plan-v1"
PROTOCOL_VERSION = "r3-benchmark-protocol-v1"
LEDGER_SCHEMA_VERSION = "permitdiff.dev/r3-discovery-ledger/v1"
SELECTION_SCHEMA_VERSION = "permitdiff.dev/r3-public-selection/v1"
RAW_LEDGER_SCHEMA_VERSION = _cb01.RAW_LEDGER_SCHEMA_VERSION
CB01_CONTRACT_VERSION = _cb01.CB01_CONTRACT_VERSION
CANONICAL_PUBLIC_PRODUCER_ID = _cb01.CANONICAL_PUBLIC_PRODUCER_ID
DEFAULT_CB01_CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)
GITHUB_API_VERSION = "2022-11-28"
API_BASE = "https://api.github.com"
SEARCH_PAGE_SIZE = 100
SEARCH_RESULT_CAP = 1000

CANDIDATE_PATHS = _cb01.CANDIDATE_PATHS
QUERY_CONCEPTS = (
    ("q1", "defaultMode dontAsk permissions allow"),
    ("q2", "permissions allow ask deny .claude settings"),
    ("q3", "WebFetch domain permissions allow"),
    ("q4", "Bash permissions allow .claude"),
    ("q5", "WebSearch permissions allow .claude"),
)
FIXED_EXCLUSION_REASONS = _cb01.FIXED_EXCLUSION_REASONS
# Deprecated Packet B2: frozen pre-exposed control retained only so existing
# v1 selection tests keep importing it. The canonical contamination source is
# the CB-01 contract register via ``contamination_status_for``.
PRE_EXPOSED_CONTROLS = frozenset(
    {
        (
            "https://github.com/SpearIT-LLC/project-framework",
            "28133b63a9a54621c8d7be879ba671daf8464c1c",
            "d8a47de7f5f96d501432a7f02c6909c667a5f31d",
            ".claude/settings.local.json",
        )
    }
)

# Raw read-phase TLS/socket truncations retried by the public-only wrapper.
# GitHubClient must preserve these through the urllib layer instead of
# converting a URLError-wrapped transient into a non-retryable DiscoveryError.
_TRANSIENT_READ_ERRORS = (IncompleteRead, RemoteDisconnected, ssl.SSLEOFError)


def _transient_reason(exc: URLError) -> BaseException | None:
    """Return the wrapped transient cause when urllib surfaces one via URLError."""

    reason = exc.reason if isinstance(exc, URLError) else None
    return reason if isinstance(reason, _TRANSIENT_READ_ERRORS) else None


class DiscoveryError(RuntimeError):
    """Raised when discovery cannot preserve the preregistered evidence contract."""


@dataclass(frozen=True)
class SearchSpec:
    """One frozen semantic query applied to one exact project-settings path."""

    query_id: str
    concept: str
    path: str
    api_query: str


def utc_now() -> str:
    """Return a UTC RFC3339 timestamp without fractional seconds."""

    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(payload: bytes) -> str:
    """Return lowercase SHA-256 for bytes."""

    return hashlib.sha256(payload).hexdigest()


def canonical_repository_url(full_name: str) -> str:
    """Return the canonical public GitHub repository URL used by the selection key.

    Packet B2: thin alias; the semantic authority is
    ``scripts.r3_cb01_corpus_construction.canonical_repository_url``.
    """

    return _cb01.canonical_repository_url(full_name)


def selection_key(
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    """Compute the preregistered deterministic public-case selection key.

    Packet B2: thin alias; the semantic authority is
    ``scripts.r3_cb01_corpus_construction.selection_key_for``.
    """

    return _cb01.selection_key_for(repository_url, baseline_commit, candidate_commit, path)


def transition_id(
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    """Return a stable identifier that is independent of discovery order.

    Packet B2: thin alias; the semantic authority is
    ``scripts.r3_cb01_corpus_construction.transition_id_for``.
    """

    return _cb01.transition_id_for(repository_url, baseline_commit, candidate_commit, path)


def _repo_root() -> Path:
    """Return the study repository root without modifying repository state."""

    return Path(__file__).resolve().parents[1]


def _load_contract_bytes(
    contract_path: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Load exact CB-01 contract bytes; hashing must use these exact bytes."""

    path = contract_path or DEFAULT_CB01_CONTRACT_PATH
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DiscoveryError(f"failed to read CB-01 contract {path}: {exc}") from exc
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"CB-01 contract is not valid JSON: {path}: {exc}") from exc
    if not isinstance(contract, dict):
        raise DiscoveryError(f"CB-01 contract must contain a JSON object: {path}")
    try:
        _cb01.validate_contract_binding(contract, raw)
    except _cb01.CB01ConstructionError as exc:
        raise DiscoveryError(f"invalid CB-01 contract: {exc}") from exc
    return contract, raw


def _study_repository_commit(repo_root: Path | None = None) -> str:
    """Record ``git rev-parse HEAD`` for a clean tree; fail closed otherwise."""

    root = repo_root or _repo_root()
    git = shutil.which("git")
    if git is None:
        raise DiscoveryError("cannot record clean study repository commit: git not found")
    try:
        head = subprocess.check_output(
            [git, "rev-parse", "HEAD"],
            cwd=str(root),
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
        status = subprocess.check_output(
            [git, "status", "--porcelain", "--untracked-files=all"],
            cwd=str(root),
            stderr=subprocess.STDOUT,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise DiscoveryError(f"cannot record clean study repository commit: {exc}") from exc
    if status.strip():
        raise DiscoveryError("study repository tree is dirty; refuse to record study commit")
    if re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise DiscoveryError("study repository commit is not a lowercase 40-hex SHA")
    return head


def _query_terms(concept: str) -> str:
    # Quoting is an allowed spelling transformation under the preregistration. Keeping
    # individual terms quoted reduces accidental stemming while preserving the concept.
    return " ".join(f'"{part}"' for part in concept.split() if part != ".claude")


def build_search_specs() -> tuple[SearchSpec, ...]:
    """Expand the five frozen concepts over the two exact candidate paths."""

    specs: list[SearchSpec] = []
    for query_id, concept in QUERY_CONCEPTS:
        terms = _query_terms(concept)
        for path in CANDIDATE_PATHS:
            filename = path.rsplit("/", 1)[1]
            api_query = f"{terms} path:.claude filename:{filename}"
            specs.append(
                SearchSpec(query_id=query_id, concept=concept, path=path, api_query=api_query)
            )
    return tuple(specs)


def _json_object(payload: bytes, *, context: str) -> dict[str, Any]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"{context} returned invalid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise DiscoveryError(f"{context} returned a non-object JSON document")
    return decoded


class GitHubClient:
    """Minimal read-only GitHub REST client with explicit pagination and no retries."""

    def __init__(self, token: str | None) -> None:
        self._token = token

    def get_json(
        self, endpoint: str, params: Mapping[str, str | int] | None = None
    ) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{API_BASE}{endpoint}{query}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "permitdiff-r3-discovery-v1",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(url, headers=headers)  # noqa: S310 - fixed HTTPS API base
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS API base
                return _json_object(response.read(), context=url)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DiscoveryError(f"GitHub API HTTP {exc.code} for {url}: {detail[:500]}") from exc
        except URLError as exc:
            transient = _transient_reason(exc)
            if transient is not None:
                raise transient from exc
            raise DiscoveryError(f"GitHub API request failed for {url}: {exc.reason}") from exc

    def search_code(self, query: str) -> tuple[list[dict[str, Any]], int, bool]:
        """Collect all accessible search results up to GitHub's 1,000-result API cap."""

        items: list[dict[str, Any]] = []
        total_count = 0
        incomplete = False
        page = 1
        while len(items) < SEARCH_RESULT_CAP:
            payload = self.get_json(
                "/search/code",
                {"q": query, "per_page": SEARCH_PAGE_SIZE, "page": page},
            )
            total_raw = payload.get("total_count")
            current = payload.get("items")
            if not isinstance(total_raw, int) or not isinstance(current, list):
                raise DiscoveryError("GitHub code search response has an unexpected shape")
            total_count = total_raw
            incomplete = incomplete or bool(payload.get("incomplete_results", False))
            typed = [item for item in current if isinstance(item, dict)]
            items.extend(typed)
            if len(current) < SEARCH_PAGE_SIZE or len(items) >= min(total_count, SEARCH_RESULT_CAP):
                break
            page += 1
        return items[:SEARCH_RESULT_CAP], total_count, incomplete

    def list_path_commits(
        self, repository: str, path: str, *, max_commits: int | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """Enumerate commit history touching one path; return records and truncation state."""

        commits: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get_json_array(
                f"/repos/{repository}/commits",
                {"path": path, "per_page": 100, "page": page},
            )
            commits.extend(payload)
            if max_commits is not None and len(commits) >= max_commits:
                return commits[:max_commits], len(payload) == 100 or len(commits) > max_commits
            if len(payload) < 100:
                return commits, False
            page += 1

    def _get_json_array(
        self, endpoint: str, params: Mapping[str, str | int] | None = None
    ) -> list[dict[str, Any]]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{API_BASE}{endpoint}{query}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "permitdiff-r3-discovery-v1",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(url, headers=headers)  # noqa: S310 - fixed HTTPS API base
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS API base
                raw = json.loads(response.read())
        except HTTPError as exc:
            raise DiscoveryError(f"GitHub API request failed for {url}: {exc}") from exc
        except URLError as exc:
            transient = _transient_reason(exc)
            if transient is not None:
                raise transient from exc
            raise DiscoveryError(f"GitHub API request failed for {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DiscoveryError(f"GitHub API request failed for {url}: {exc}") from exc
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise DiscoveryError(f"GitHub API returned unexpected array payload for {url}")
        return raw

    def get_commit(self, repository: str, commit: str) -> dict[str, Any]:
        return self.get_json(f"/repos/{repository}/commits/{commit}")

    def get_file(self, repository: str, path: str, ref: str) -> tuple[dict[str, Any], bytes]:
        encoded_path = quote(path, safe="/")
        payload = self.get_json(f"/repos/{repository}/contents/{encoded_path}", {"ref": ref})
        if payload.get("type") != "file":
            raise DiscoveryError(f"{repository}:{path}@{ref} is not a regular GitHub file")
        content = payload.get("content")
        encoding = payload.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            raise DiscoveryError(f"{repository}:{path}@{ref} has unavailable inline file bytes")
        try:
            raw = base64.b64decode(content, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise DiscoveryError(f"{repository}:{path}@{ref} has invalid base64 content") from exc
        return payload, raw


def _repository_full_name(item: Mapping[str, Any]) -> str | None:
    repository = item.get("repository")
    if not isinstance(repository, Mapping):
        return None
    full_name = repository.get("full_name")
    return full_name if isinstance(full_name, str) else None


def _exact_candidate_path(path: str) -> bool:
    return path in CANDIDATE_PATHS


def discover_locations(
    client: GitHubClient,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Run every frozen query and return deduplicated exact-path locations plus query evidence."""

    locations: dict[tuple[str, str], dict[str, Any]] = {}
    query_evidence: list[dict[str, Any]] = []
    complete = True

    for spec in build_search_specs():
        items, total_count, incomplete = client.search_code(spec.api_query)
        capped = total_count > SEARCH_RESULT_CAP
        complete = complete and not incomplete and not capped
        exact_count = 0
        for item in items:
            path = item.get("path")
            repository = _repository_full_name(item)
            if not isinstance(path, str) or repository is None or not _exact_candidate_path(path):
                continue
            exact_count += 1
            key = (repository, path)
            entry = locations.setdefault(
                key,
                {
                    "repository_full_name": repository,
                    "repository_url": canonical_repository_url(repository),
                    "path": path,
                    "discovered_by": [],
                    "default_branch_blob": item.get("sha"),
                    "default_branch_html_url": item.get("html_url"),
                },
            )
            discovered_by = entry["discovered_by"]
            if not isinstance(discovered_by, list):
                raise DiscoveryError("internal discovery ledger has malformed discovered_by")
            marker = {"query_id": spec.query_id, "candidate_path": spec.path}
            if marker not in discovered_by:
                discovered_by.append(marker)

        query_evidence.append(
            {
                "query_id": spec.query_id,
                "concept": spec.concept,
                "candidate_path": spec.path,
                "api_query": spec.api_query,
                "reported_total_count": total_count,
                "retrieved_count": len(items),
                "exact_candidate_path_count": exact_count,
                "incomplete_results": incomplete,
                "api_result_cap_reached": capped,
            }
        )

    ordered_locations = sorted(
        locations.values(), key=lambda item: (str(item["repository_full_name"]), str(item["path"]))
    )
    return ordered_locations, query_evidence, complete


def _commit_sha(record: Mapping[str, Any], *, context: str) -> str:
    sha = record.get("sha")
    if not isinstance(sha, str) or len(sha) != 40:
        raise DiscoveryError(f"{context} has invalid commit SHA")
    return sha


def _commit_timestamp(record: Mapping[str, Any]) -> str | None:
    commit = record.get("commit")
    if not isinstance(commit, Mapping):
        return None
    committer = commit.get("committer")
    if not isinstance(committer, Mapping):
        return None
    date = committer.get("date")
    return date if isinstance(date, str) else None


def _parse_json_object(raw: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _file_state(
    client: GitHubClient, repository: str, path: str, commit: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    metadata, raw = client.get_file(repository, path, commit)
    blob = metadata.get("sha")
    if not isinstance(blob, str) or len(blob) != 40:
        raise DiscoveryError(f"{repository}:{path}@{commit} has invalid blob SHA")
    state = {
        "commit": commit,
        "blob": blob,
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
    }
    return state, _parse_json_object(raw)


def _permissions_changed(
    baseline_payload: Mapping[str, Any], candidate_payload: Mapping[str, Any]
) -> bool:
    return baseline_payload.get("permissions") != candidate_payload.get("permissions")


def _candidate_parent_count(client: GitHubClient, repository: str, commit: str) -> int:
    payload = client.get_commit(repository, commit)
    parents = payload.get("parents")
    if not isinstance(parents, list):
        raise DiscoveryError(f"{repository}@{commit} has unavailable parent metadata")
    return len(parents)


def _control_status(
    repository_url: str,
    baseline_commit: str,
    candidate_commit: str,
    path: str,
    contract: Mapping[str, Any],
) -> str:
    """Recompute contamination from the CB-01 contract register (never trust stored)."""

    return _cb01.contamination_status_for(
        repository_url, baseline_commit, candidate_commit, path, contract
    )


def enumerate_transitions(
    client: GitHubClient,
    locations: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    *,
    max_history_commits: int | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Enumerate adjacent versions of every discovered exact project-settings path."""

    transitions: list[dict[str, Any]] = []
    complete = True
    seen: set[tuple[str, str, str, str]] = set()

    for location in locations:
        repository = str(location["repository_full_name"])
        repository_url = str(location["repository_url"])
        path = str(location["path"])
        commits, truncated = client.list_path_commits(
            repository, path, max_commits=max_history_commits
        )
        complete = complete and not truncated
        if len(commits) < 2:
            continue

        for candidate_record, baseline_record in pairwise(commits):
            candidate_commit = _commit_sha(candidate_record, context=f"{repository}:{path}")
            baseline_commit = _commit_sha(baseline_record, context=f"{repository}:{path}")
            identity = (repository_url, baseline_commit, candidate_commit, path)
            if identity in seen:
                continue
            seen.add(identity)

            exclusion_reasons: list[str] = []
            screening_status = "pending"
            baseline_state: dict[str, Any] | None = None
            candidate_state: dict[str, Any] | None = None
            permissions_changed: bool | None = None
            parent_count: int | None = None

            try:
                parent_count = _candidate_parent_count(client, repository, candidate_commit)
                baseline_state, baseline_json = _file_state(
                    client, repository, path, baseline_commit
                )
                candidate_state, candidate_json = _file_state(
                    client, repository, path, candidate_commit
                )
            except DiscoveryError:
                screening_status = "excluded"
                exclusion_reasons.append("unavailable_provenance")
                baseline_json = None
                candidate_json = None

            if screening_status != "excluded":
                if parent_count is not None and parent_count > 1:
                    screening_status = "excluded"
                    exclusion_reasons.append("ambiguous_parent_transition")
                if baseline_json is None or candidate_json is None:
                    screening_status = "excluded"
                    exclusion_reasons.append("artifact_parse_failure")
                else:
                    permissions_changed = _permissions_changed(baseline_json, candidate_json)

            contamination = _control_status(
                repository_url, baseline_commit, candidate_commit, path, contract
            )
            if contamination == "pre_exposed_engineering_control":
                screening_status = "excluded"
                if "pre_exposed_engineering_control" not in exclusion_reasons:
                    exclusion_reasons.append("pre_exposed_engineering_control")

            transitions.append(
                {
                    "transition_id": _cb01.transition_id_for(
                        repository_url, baseline_commit, candidate_commit, path
                    ),
                    "discovered_by": location.get("discovered_by", []),
                    "repository_full_name": repository,
                    "repository_url": repository_url,
                    "path": path,
                    "baseline_commit": baseline_commit,
                    "candidate_commit": candidate_commit,
                    "baseline_blob": None if baseline_state is None else baseline_state["blob"],
                    "candidate_blob": None if candidate_state is None else candidate_state["blob"],
                    "baseline_sha256": None if baseline_state is None else baseline_state["sha256"],
                    "candidate_sha256": (
                        None if candidate_state is None else candidate_state["sha256"]
                    ),
                    "baseline_size_bytes": None
                    if baseline_state is None
                    else baseline_state["size_bytes"],
                    "candidate_size_bytes": None
                    if candidate_state is None
                    else candidate_state["size_bytes"],
                    "candidate_commit_timestamp": _commit_timestamp(candidate_record),
                    "candidate_parent_count": parent_count,
                    "permissions_changed": permissions_changed,
                    "screening_status": screening_status,
                    "exclusion_reasons": sorted(set(exclusion_reasons)),
                    "contamination_status": contamination,
                    "selection_key": _cb01.selection_key_for(
                        repository_url, baseline_commit, candidate_commit, path
                    ),
                    "manual_review_required": screening_status == "pending",
                }
            )

    transitions.sort(key=lambda item: str(item["selection_key"]))
    return transitions, complete


def build_ledger(
    client: GitHubClient,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
    study_repository_commit: str,
    *,
    max_history_commits: int | None = None,
) -> dict[str, Any]:
    """Collect a raw public discovery v2 ledger without executing PermitDiff."""

    try:
        _cb01.validate_contract_binding(contract, contract_bytes)
    except _cb01.CB01ConstructionError as exc:
        raise DiscoveryError(f"invalid CB-01 contract: {exc}") from exc
    if re.fullmatch(r"[0-9a-f]{40}", study_repository_commit) is None:
        raise DiscoveryError("study repository commit is not a lowercase 40-hex SHA")
    started_at = utc_now()
    locations, queries, search_complete = discover_locations(client)
    transitions, history_complete = enumerate_transitions(
        client, locations, contract, max_history_commits=max_history_commits
    )
    complete = search_complete and history_complete
    return {
        "schema_version": RAW_LEDGER_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "cb01_contract_version": CB01_CONTRACT_VERSION,
        "cb01_contract_sha256": _cb01.sha256_bytes(contract_bytes),
        "study_repository_commit": study_repository_commit,
        "producer_id": CANONICAL_PUBLIC_PRODUCER_ID,
        "source": "github-rest-code-search-and-commit-history",
        "generated_at": started_at,
        "discovery_complete": complete,
        "limitations": [
            "GitHub code search discovers paths indexed on repository default branches; deleted or "
            "otherwise unindexed historical settings paths are outside this discovery frame.",
            "GitHub code search exposes at most 1,000 results per query; any capped or incomplete "
            "query makes discovery_complete=false.",
            (
                "Pending transitions still require manual review for public semantics, sensitive "
                "content, project scope, and non-cosmetic duplication before they can become "
                "eligible."
            ),
        ],
        "queries": queries,
        "discovered_location_count": len(locations),
        "transition_count": len(transitions),
        "transitions": transitions,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscoveryError(f"failed to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DiscoveryError(f"expected a JSON object in {path}")
    return payload


def _read_json_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    """Read exact file bytes plus the parsed JSON object (no reserialization)."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DiscoveryError(f"failed to read JSON {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"failed to read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DiscoveryError(f"expected a JSON object in {path}")
    return payload, raw


def select_public_historical(
    screened: Mapping[str, Any],
    screened_bytes: bytes,
    contract: Mapping[str, Any],
    contract_bytes: bytes,
) -> dict[str, Any]:
    """Derive public selection v2 via the CB-01 single source of truth.

    Packet B4: thin wrapper around ``cb01.derive_selection_v2``. No
    eligibility filtering, sorting, cap, truncation, key recomputation, or
    digest logic lives here. Frozen target (18), cap (2), and minimum (12)
    are enforced inside CB-01; below-minimum raises instead of returning a
    canonical payload.
    """

    try:
        return _cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    except _cb01.CB01ConstructionError as exc:
        raise DiscoveryError(str(exc)) from exc


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _resolve_token() -> str | None:
    return os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="collect the preregistered GitHub ledger")
    discover.add_argument("--output", type=Path, required=True)
    discover.add_argument(
        "--max-history-commits",
        type=int,
        help="debug-only cap per path; any cap reached marks the ledger incomplete",
    )
    discover.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="CB-01 contract file; defaults to the committed contract",
    )
    discover.add_argument(
        "--study-commit",
        type=str,
        default=None,
        help="study repository commit; defaults to clean git rev-parse HEAD",
    )

    select = subparsers.add_parser("select", help="select from a fully screened ledger")
    select.add_argument("--ledger", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--target", type=int, default=18)
    select.add_argument("--max-per-repository", type=int, default=2)
    select.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="CB-01 contract file; defaults to the committed contract",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "discover":
            if args.max_history_commits is not None and args.max_history_commits < 2:
                raise DiscoveryError("--max-history-commits must be at least 2")
            contract, contract_bytes = _load_contract_bytes(args.contract)
            study_commit = args.study_commit or _study_repository_commit()
            ledger = build_ledger(
                GitHubClient(_resolve_token()),
                contract,
                contract_bytes,
                study_commit,
                max_history_commits=args.max_history_commits,
            )
            _write_json(args.output, ledger)
            if ledger["discovery_complete"] is not True:
                print(
                    "R3 discovery completed with an incomplete frame; do not select cases from it.",
                    file=sys.stderr,
                )
                return 2
            return 0

        if args.target != TARGET_CASES:
            raise DiscoveryError(
                f"R3 selection target must remain exactly {TARGET_CASES}"
            )
        if args.max_per_repository != MAX_CASES_PER_REPOSITORY:
            raise DiscoveryError(
                f"R3 per-repository cap must remain exactly {MAX_CASES_PER_REPOSITORY}"
            )
        screened, screened_bytes = _read_json_bytes(args.ledger)
        contract, contract_bytes = _load_contract_bytes(args.contract)
        result = select_public_historical(
            screened,
            screened_bytes,
            contract,
            contract_bytes,
        )
        _write_json(args.output, result)
        return 0
    except DiscoveryError as exc:
        print(f"R3 discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
