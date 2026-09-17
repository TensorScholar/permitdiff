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
import ssl
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import IncompleteRead, RemoteDisconnected
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

PLAN_VERSION = "r3-exploratory-corpus-plan-v1"
PROTOCOL_VERSION = "r3-benchmark-protocol-v1"
LEDGER_SCHEMA_VERSION = "permitdiff.dev/r3-discovery-ledger/v1"
SELECTION_SCHEMA_VERSION = "permitdiff.dev/r3-public-selection/v1"
GITHUB_API_VERSION = "2022-11-28"
API_BASE = "https://api.github.com"
SEARCH_PAGE_SIZE = 100
SEARCH_RESULT_CAP = 1000

CANDIDATE_PATHS = (".claude/settings.json", ".claude/settings.local.json")
QUERY_CONCEPTS = (
    ("q1", "defaultMode dontAsk permissions allow"),
    ("q2", "permissions allow ask deny .claude settings"),
    ("q3", "WebFetch domain permissions allow"),
    ("q4", "Bash permissions allow .claude"),
    ("q5", "WebSearch permissions allow .claude"),
)
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
    """Return the canonical public GitHub repository URL used by the selection key."""

    return f"https://github.com/{full_name}"


def selection_key(
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    """Compute the preregistered deterministic public-case selection key."""

    material = f"{repository_url}\n{baseline_commit}\n{candidate_commit}\n{path}".encode()
    return sha256_bytes(material)


def transition_id(
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    """Return a stable identifier that is independent of discovery order."""

    return "gh-" + selection_key(repository_url, baseline_commit, candidate_commit, path)[:20]


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
    repository_url: str, baseline_commit: str, candidate_commit: str, path: str
) -> str:
    key = (repository_url, baseline_commit, candidate_commit, path)
    return "pre_exposed_engineering_control" if key in PRE_EXPOSED_CONTROLS else "clean"


def enumerate_transitions(
    client: GitHubClient,
    locations: Sequence[Mapping[str, Any]],
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

            contamination = _control_status(repository_url, baseline_commit, candidate_commit, path)
            if contamination == "pre_exposed_engineering_control":
                screening_status = "excluded"
                if "pre_exposed_engineering_control" not in exclusion_reasons:
                    exclusion_reasons.append("pre_exposed_engineering_control")

            transitions.append(
                {
                    "transition_id": transition_id(
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
                    "selection_key": selection_key(
                        repository_url, baseline_commit, candidate_commit, path
                    ),
                    "manual_review_required": screening_status == "pending",
                }
            )

    transitions.sort(key=lambda item: str(item["selection_key"]))
    return transitions, complete


def build_ledger(client: GitHubClient, *, max_history_commits: int | None = None) -> dict[str, Any]:
    """Collect a discovery ledger without executing PermitDiff."""

    started_at = utc_now()
    locations, queries, search_complete = discover_locations(client)
    transitions, history_complete = enumerate_transitions(
        client, locations, max_history_commits=max_history_commits
    )
    complete = search_complete and history_complete
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "generated_at": started_at,
        "source": "github-rest-code-search-and-commit-history",
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


def _validate_exclusion_reasons(transitions: Iterable[Mapping[str, Any]]) -> None:
    for transition in transitions:
        reasons = transition.get("exclusion_reasons", [])
        if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
            raise DiscoveryError("ledger contains malformed exclusion reasons")
        unknown = set(reasons) - FIXED_EXCLUSION_REASONS
        if unknown:
            raise DiscoveryError(
                f"ledger uses non-preregistered exclusion reasons: {sorted(unknown)}"
            )


def select_public_historical(
    ledger: Mapping[str, Any], *, target: int = 18, max_per_repository: int = 2
) -> dict[str, Any]:
    """Select eligible transitions strictly by the preregistered SHA-256 ordering."""

    if ledger.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise DiscoveryError("unsupported discovery ledger schema version")
    if ledger.get("plan_version") != PLAN_VERSION:
        raise DiscoveryError("ledger plan version does not match the preregistered plan")
    if ledger.get("discovery_complete") is not True:
        raise DiscoveryError("cannot select from an incomplete discovery ledger")
    raw_transitions = ledger.get("transitions")
    if not isinstance(raw_transitions, list):
        raise DiscoveryError("ledger transitions must be a list")
    transitions = [item for item in raw_transitions if isinstance(item, Mapping)]
    if len(transitions) != len(raw_transitions):
        raise DiscoveryError("ledger contains a non-object transition")
    _validate_exclusion_reasons(transitions)

    eligible: list[Mapping[str, Any]] = []
    for item in transitions:
        if item.get("screening_status") != "eligible":
            continue
        if item.get("contamination_status") != "clean":
            raise DiscoveryError("eligible transition cannot be contaminated")
        expected_key = selection_key(
            str(item["repository_url"]),
            str(item["baseline_commit"]),
            str(item["candidate_commit"]),
            str(item["path"]),
        )
        if item.get("selection_key") != expected_key:
            raise DiscoveryError(f"selection key mismatch for {item.get('transition_id')}")
        eligible.append(item)

    eligible.sort(key=lambda item: str(item["selection_key"]))
    selected: list[dict[str, Any]] = []
    repo_counts: defaultdict[str, int] = defaultdict(int)
    for item in eligible:
        repository = str(item["repository_full_name"])
        if repo_counts[repository] >= max_per_repository:
            continue
        selected.append(
            {
                "rank": len(selected) + 1,
                "transition_id": item["transition_id"],
                "repository_full_name": repository,
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
        repo_counts[repository] += 1
        if len(selected) == target:
            break

    return {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "plan_version": PLAN_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "source_ledger_sha256": sha256_bytes(
            json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ),
        "target_cases": target,
        "max_cases_per_repository": max_per_repository,
        "eligible_case_count": len(eligible),
        "selected_case_count": len(selected),
        "shortfall": max(0, target - len(selected)),
        "selected": selected,
    }


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

    select = subparsers.add_parser("select", help="select from a fully screened ledger")
    select.add_argument("--ledger", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--target", type=int, default=18)
    select.add_argument("--max-per-repository", type=int, default=2)

    args = parser.parse_args(argv)
    try:
        if args.command == "discover":
            if args.max_history_commits is not None and args.max_history_commits < 2:
                raise DiscoveryError("--max-history-commits must be at least 2")
            ledger = build_ledger(
                GitHubClient(_resolve_token()),
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

        if args.target < 1 or args.max_per_repository < 1:
            raise DiscoveryError("selection target and per-repository cap must be positive")
        ledger = _read_json(args.ledger)
        result = select_public_historical(
            ledger,
            target=args.target,
            max_per_repository=args.max_per_repository,
        )
        _write_json(args.output, result)
        return 0
    except DiscoveryError as exc:
        print(f"R3 discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
