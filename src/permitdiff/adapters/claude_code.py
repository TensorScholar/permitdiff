"""Conservative normalization of Claude Code project pre-approval changes.

This adapter intentionally models a narrow release-review surface rather than claiming
full Claude Code effective authority. It accepts ``dontAsk`` settings pairs only when
``deny`` and ``ask`` rules are unchanged, translates a documented subset of allow rules,
and rejects changed semantics that cannot be represented faithfully by PermitDiff.
"""

from __future__ import annotations

import hashlib
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from permitdiff.models import DecisionEffect
from permitdiff.policy import PolicyDocument, PolicyMetadata, PolicyRule, Predicate, RuleMatch

_MAX_SETTINGS_BYTES = 1_000_000
_ALLOWED_PERMISSION_KEYS = frozenset({"allow", "ask", "deny", "defaultMode"})
_RULE_RE = re.compile(r"^(?P<tool>[A-Za-z][A-Za-z0-9_]*)(?:\((?P<specifier>.*)\))?$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9.-]+$")


class ClaudeAdapterError(ValueError):
    """Raised when native Claude semantics fall outside the proven adapter boundary."""


class ClaudePreapprovalEvidence(BaseModel):
    """Machine-readable evidence for one bounded native-settings normalization."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["permitdiff.claude-preapproval/v1alpha1"] = (
        "permitdiff.claude-preapproval/v1alpha1"
    )
    adapter: Literal["claude-code-project-preapprovals"] = "claude-code-project-preapprovals"
    baseline_source_sha256: str
    candidate_source_sha256: str
    default_mode: Literal["dontAsk"] = "dontAsk"
    shared_deny_rule_count: int
    shared_ask_rule_count: int
    shared_restrictive_rules_sha256: str
    shared_opaque_allow_rules: list[str]
    baseline_redundant_allow_rules: list[str]
    candidate_redundant_allow_rules: list[str]
    baseline_translated_allow_rules: list[str]
    candidate_translated_allow_rules: list[str]
    ignored_baseline_root_keys: list[str]
    ignored_candidate_root_keys: list[str]
    changed_ignored_root_keys: list[str]
    claim_boundary: list[str]


class ClaudePreapprovalPair(BaseModel):
    """Normalized baseline/candidate policies plus native-source evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_policy: PolicyDocument
    candidate_policy: PolicyDocument
    evidence: ClaudePreapprovalEvidence


class _LoadedSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_sha256: str
    allow: list[str]
    ask: list[str]
    deny: list[str]
    default_mode: str
    ignored_root: dict[str, Any]


class _AllowSurface(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bare_tools: list[str]
    webfetch_domains: list[str]
    opaque_rules: list[str]
    redundant_rules: list[str]
    translated_rules: list[str]


def normalize_claude_preapproval_pair(
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> ClaudePreapprovalPair:
    """Normalize a bounded Claude ``dontAsk`` pre-approval delta into PermitDiff policies.

    The initial adapter deliberately requires deny/ask context to be unchanged. Changed
    unsupported allow semantics are rejected. Unchanged unsupported allow rules may be
    carried as opaque evidence only when no translated change touches the same tool.
    Non-permission root changes are surfaced as evidence but are outside this projection.
    """

    baseline = _load_settings(Path(baseline_path))
    candidate = _load_settings(Path(candidate_path))

    if baseline.default_mode != "dontAsk" or candidate.default_mode != "dontAsk":
        raise ClaudeAdapterError(
            "Claude native adapter currently supports only explicit defaultMode='dontAsk'"
        )

    baseline_ask = sorted(set(baseline.ask))
    candidate_ask = sorted(set(candidate.ask))
    baseline_deny = sorted(set(baseline.deny))
    candidate_deny = sorted(set(candidate.deny))
    if baseline_ask != candidate_ask or baseline_deny != candidate_deny:
        raise ClaudeAdapterError(
            "initial Claude preapproval adapter requires deny and ask rules to remain unchanged"
        )

    baseline_surface = _normalize_allow_surface(baseline.allow)
    candidate_surface = _normalize_allow_surface(candidate.allow)

    if baseline_surface.opaque_rules != candidate_surface.opaque_rules:
        raise ClaudeAdapterError(
            "unsupported Claude allow rules changed; refusing to approximate native semantics"
        )

    changed_tools = _changed_translated_tools(baseline_surface, candidate_surface)
    opaque_tools = {_tool_name(rule) for rule in baseline_surface.opaque_rules}
    conflicting_opaque = sorted(changed_tools & opaque_tools)
    if conflicting_opaque:
        raise ClaudeAdapterError(
            "translated allow changes overlap unchanged unsupported allow rules for tools: "
            + ", ".join(conflicting_opaque)
        )

    restrictive_rules = [*baseline_deny, *baseline_ask]
    shadowing = sorted(
        tool
        for tool in changed_tools
        if any(_tool_pattern_may_match(_tool_name(rule), tool) for rule in restrictive_rules)
    )
    if shadowing:
        raise ClaudeAdapterError(
            "translated allow changes overlap unchanged deny/ask rules for tools: "
            + ", ".join(shadowing)
            + "; refusing to claim an effective preapproval expansion"
        )

    baseline_policy = _policy_from_surface(
        baseline_surface,
        source_sha256=baseline.source_sha256,
        role="baseline",
    )
    candidate_policy = _policy_from_surface(
        candidate_surface,
        source_sha256=candidate.source_sha256,
        role="candidate",
    )

    restrictive_digest = hashlib.sha256(
        json.dumps(
            {"ask": baseline_ask, "deny": baseline_deny},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    evidence = ClaudePreapprovalEvidence(
        baseline_source_sha256=baseline.source_sha256,
        candidate_source_sha256=candidate.source_sha256,
        shared_deny_rule_count=len(baseline_deny),
        shared_ask_rule_count=len(baseline_ask),
        shared_restrictive_rules_sha256=restrictive_digest,
        shared_opaque_allow_rules=baseline_surface.opaque_rules,
        baseline_redundant_allow_rules=baseline_surface.redundant_rules,
        candidate_redundant_allow_rules=candidate_surface.redundant_rules,
        baseline_translated_allow_rules=baseline_surface.translated_rules,
        candidate_translated_allow_rules=candidate_surface.translated_rules,
        ignored_baseline_root_keys=sorted(baseline.ignored_root),
        ignored_candidate_root_keys=sorted(candidate.ignored_root),
        changed_ignored_root_keys=_changed_root_keys(
            baseline.ignored_root,
            candidate.ignored_root,
        ),
        claim_boundary=[
            "Models only project settings permissions.allow preapproval changes under explicit dontAsk.",
            "Requires permissions.deny and permissions.ask to be unchanged across the pair.",
            (
                "Non-permissions root settings are not modeled; changed root key names are "
                "surfaced separately in this evidence."
            ),
            (
                "Exact WebFetch(domain:HOST) rules are modeled only as WebFetch preapprovals; "
                "Claude Code can also apply domain rules to sandbox network policy, which is "
                "outside this projection."
            ),
            (
                "Does not model user/managed overrides, hooks, sandbox policy, built-in tool "
                "exceptions, or other permission modes."
            ),
            (
                "WebFetch domain rules require normalized _claude.permission_domain metadata "
                "in review scenarios."
            ),
            "Unsupported changed native semantics fail closed instead of being approximated.",
        ],
    )
    return ClaudePreapprovalPair(
        baseline_policy=baseline_policy,
        candidate_policy=candidate_policy,
        evidence=evidence,
    )


def _load_settings(path: Path) -> _LoadedSettings:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise ClaudeAdapterError(f"failed to read Claude settings {path}: {exc}") from exc
    if len(raw_bytes) > _MAX_SETTINGS_BYTES:
        raise ClaudeAdapterError(f"Claude settings exceed {_MAX_SETTINGS_BYTES} bytes")
    try:
        text = raw_bytes.decode("utf-8")
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ClaudeAdapterError(f"invalid Claude settings {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ClaudeAdapterError("Claude settings root must be a JSON object")
    permissions = raw.get("permissions")
    if not isinstance(permissions, dict):
        raise ClaudeAdapterError("Claude settings must contain a permissions object")
    unknown_keys = sorted(set(permissions) - _ALLOWED_PERMISSION_KEYS)
    if unknown_keys:
        raise ClaudeAdapterError(
            "unsupported keys inside Claude permissions: " + ", ".join(unknown_keys)
        )

    return _LoadedSettings(
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        allow=_string_list(permissions, "allow"),
        ask=_string_list(permissions, "ask"),
        deny=_string_list(permissions, "deny"),
        default_mode=_required_string(permissions, "defaultMode"),
        ignored_root={key: value for key, value in raw.items() if key != "permissions"},
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _string_list(document: dict[str, Any], key: str) -> list[str]:
    value = document.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ClaudeAdapterError(f"permissions.{key} must be an array of strings")
    normalized = [item.strip() for item in value]
    if any(not item for item in normalized):
        raise ClaudeAdapterError(f"permissions.{key} must not contain empty rules")
    return normalized


def _required_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ClaudeAdapterError(f"permissions.{key} must be a non-empty string")
    return value.strip()


def _changed_root_keys(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    keys = set(baseline) | set(candidate)
    return sorted(
        key
        for key in keys
        if key not in baseline or key not in candidate or baseline[key] != candidate[key]
    )


def _normalize_allow_surface(rules: list[str]) -> _AllowSurface:
    unique_rules: list[str] = []
    redundant: list[str] = []
    seen_raw: set[str] = set()
    for rule in rules:
        if rule in seen_raw:
            redundant.append(rule)
            continue
        seen_raw.add(rule)
        unique_rules.append(rule)

    parsed = [(_parse_rule_shape(rule), rule) for rule in unique_rules]
    bare_tools = {tool for (tool, specifier), _ in parsed if _is_bare_equivalent(tool, specifier)}

    translated_bare: set[str] = set()
    webfetch_domains: set[str] = set()
    opaque: list[str] = []
    semantic_seen: set[tuple[str, str]] = set()

    for (tool, specifier), source_rule in parsed:
        is_bare = _is_bare_equivalent(tool, specifier)
        if not is_bare and tool in bare_tools:
            redundant.append(source_rule)
            continue
        if is_bare:
            semantic = ("bare", tool)
            if semantic in semantic_seen:
                redundant.append(source_rule)
                continue
            semantic_seen.add(semantic)
            translated_bare.add(tool)
            continue
        if specifier is None:  # pragma: no cover - handled by _is_bare_equivalent
            raise AssertionError("bare Claude rule was not recognized")
        domain = _exact_webfetch_domain(tool, specifier)
        if domain is not None:
            semantic = ("webfetch-domain", domain)
            if semantic in semantic_seen:
                redundant.append(source_rule)
                continue
            semantic_seen.add(semantic)
            webfetch_domains.add(domain)
            continue
        opaque.append(source_rule)

    translated_rules = [*sorted(translated_bare)]
    translated_rules.extend(f"WebFetch(domain:{domain})" for domain in sorted(webfetch_domains))
    return _AllowSurface(
        bare_tools=sorted(translated_bare),
        webfetch_domains=sorted(webfetch_domains),
        opaque_rules=sorted(opaque),
        redundant_rules=sorted(redundant),
        translated_rules=translated_rules,
    )


def _parse_rule_shape(rule: str) -> tuple[str, str | None]:
    match = _RULE_RE.fullmatch(rule)
    if match is None:
        raise ClaudeAdapterError(f"invalid or unsupported Claude permission rule syntax: {rule!r}")
    tool = match.group("tool")
    specifier = match.group("specifier")
    if specifier is not None:
        specifier = specifier.strip()
        if not specifier:
            raise ClaudeAdapterError(f"empty Claude permission specifier: {rule!r}")
    return tool, specifier


def _is_bare_equivalent(tool: str, specifier: str | None) -> bool:
    if specifier is None:
        return True
    return tool in {"Bash", "PowerShell"} and specifier == "*"


def _exact_webfetch_domain(tool: str, specifier: str) -> str | None:
    if tool != "WebFetch" or not specifier.startswith("domain:"):
        return None
    domain = specifier.removeprefix("domain:").strip()
    if not domain or "*" in domain or not _DOMAIN_RE.fullmatch(domain):
        return None
    normalized = domain.lower().rstrip(".")
    return normalized or None


def _tool_name(rule: str) -> str:
    match = re.match(r"^([^()]+)", rule)
    if match is None or not match.group(1).strip():
        raise ClaudeAdapterError(f"cannot determine Claude tool name from rule {rule!r}")
    return match.group(1).strip()


def _tool_pattern_may_match(pattern: str, tool: str) -> bool:
    if any(character in pattern for character in "?["):
        return True
    return fnmatchcase(tool, pattern) if "*" in pattern else tool == pattern


def _changed_translated_tools(baseline: _AllowSurface, candidate: _AllowSurface) -> set[str]:
    changed = set(baseline.bare_tools) ^ set(candidate.bare_tools)
    if baseline.webfetch_domains != candidate.webfetch_domains:
        changed.add("WebFetch")
    return changed


def _policy_from_surface(
    surface: _AllowSurface,
    *,
    source_sha256: str,
    role: str,
) -> PolicyDocument:
    rules: list[PolicyRule] = []
    if surface.bare_tools:
        rules.append(
            PolicyRule(
                id="claude-allow-tools",
                description="Claude Code project-level bare-tool pre-approvals.",
                effect=DecisionEffect.ALLOW,
                match=RuleMatch(tools=surface.bare_tools, agents=["claude-code"]),
            )
        )
    if surface.webfetch_domains:
        rules.append(
            PolicyRule(
                id="claude-allow-webfetch-domains",
                description="Claude Code project-level WebFetch domain pre-approvals.",
                effect=DecisionEffect.ALLOW,
                match=RuleMatch(
                    tools=["WebFetch"],
                    agents=["claude-code"],
                    arguments=[
                        Predicate(
                            path="_claude.permission_domain",
                            operator="in",
                            value=surface.webfetch_domains,
                        )
                    ],
                ),
            )
        )
    return PolicyDocument(
        metadata=PolicyMetadata(
            name="claude-code-project-preapprovals",
            version=f"{role}-{source_sha256[:12]}",
            description=(
                "Bounded normalization of Claude Code permissions.allow under unchanged "
                "dontAsk deny/ask context."
            ),
        ),
        default_effect=DecisionEffect.DENY,
        rules=rules,
    )
