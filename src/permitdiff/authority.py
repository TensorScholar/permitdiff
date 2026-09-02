"""Conservative static analysis of policy changes that may alter effective authority."""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from fnmatch import fnmatchcase
from typing import Any

from pydantic import BaseModel, ConfigDict

from permitdiff.models import DecisionEffect
from permitdiff.policy import PolicyDocument, PolicyRule, Predicate, RuleMatch

_EFFECT_RANK = {
    DecisionEffect.DENY: 0,
    DecisionEffect.REQUIRE_APPROVAL: 1,
    DecisionEffect.ALLOW: 2,
}
_GLOB_FIELDS = ("tools", "principals", "agents", "environments", "sources")
_BOOL_FIELDS = (
    "security_metadata_trusted",
    "read_only",
    "destructive",
    "idempotent",
    "open_world",
)


class MatchRelation(StrEnum):
    """Conservative containment relation for candidate versus baseline match sets."""

    EQUAL = "equal"
    BROADER = "broader"
    NARROWER = "narrower"
    INCOMPARABLE = "incomparable"
    UNKNOWN = "unknown"


class AuthorityFindingKind(StrEnum):
    """Gate-relevant conclusion from bounded static analysis."""

    POTENTIAL_EXPANSION = "potential_expansion"
    UNKNOWN = "unknown"


class AuthorityFinding(BaseModel):
    """One deterministic static finding about a policy change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str
    kind: AuthorityFindingKind
    code: str
    baseline_rule_id: str | None
    candidate_rule_id: str | None
    baseline_effect: DecisionEffect | None
    candidate_effect: DecisionEffect | None
    match_relation: MatchRelation | None
    message: str


def semantic_rule_payload(rule: PolicyRule) -> dict[str, Any]:
    """Canonical permission semantics for a rule, excluding ID and description."""

    match = rule.match.model_dump(mode="json")
    for field_name in _GLOB_FIELDS:
        match[field_name] = sorted(set(match[field_name]))
    match["risks"] = sorted(set(match["risks"]))
    arguments = {
        json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        for item in match["arguments"]
    }
    match["arguments"] = [json.loads(item) for item in sorted(arguments)]
    return {"effect": rule.effect.value, "match": match}


def analyze_authority_changes(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
) -> list[AuthorityFinding]:
    """Return only expansions or changes that cannot be proved non-expanding."""

    findings: list[AuthorityFinding] = []
    baseline_by_id = {rule.id: rule for rule in baseline.rules}
    candidate_by_id = {rule.id: rule for rule in candidate.rules}
    baseline_pos = {rule.id: index for index, rule in enumerate(baseline.rules)}
    candidate_pos = {rule.id: index for index, rule in enumerate(candidate.rules)}
    shared = set(baseline_by_id) & set(candidate_by_id)
    removed = set(baseline_by_id) - set(candidate_by_id)
    added = set(candidate_by_id) - set(baseline_by_id)

    renames = _same_position_renames(baseline, candidate, removed, added)
    for old_id, new_id in renames:
        removed.discard(old_id)
        added.discard(new_id)

    for rule_id in sorted(shared):
        before = baseline_by_id[rule_id]
        after = candidate_by_id[rule_id]
        if semantic_rule_payload(before) == semantic_rule_payload(after):
            continue
        relation = match_relation(before.match, after.match)
        kind = _classify_rule_change(before.effect, after.effect, relation)
        if kind is None:
            continue
        findings.append(
            _finding(
                kind=kind,
                code=_rule_change_code(before.effect, after.effect, relation),
                before=before,
                after=after,
                before_pos=baseline_pos[rule_id],
                after_pos=candidate_pos[rule_id],
                relation=relation,
                message=_rule_change_message(rule_id, before.effect, after.effect, relation, kind),
            )
        )

    for rule_id in sorted(added):
        rule = candidate_by_id[rule_id]
        if rule.effect is DecisionEffect.DENY:
            continue
        findings.append(
            _finding(
                kind=AuthorityFindingKind.POTENTIAL_EXPANSION,
                code="rule_added",
                before=None,
                after=rule,
                before_pos=None,
                after_pos=candidate_pos[rule_id],
                relation=None,
                message=(
                    f"Candidate adds {rule.effect.value} rule {rule_id!r}; "
                    "the rule can make previously less-permissive requests reachable."
                ),
            )
        )

    for rule_id in sorted(removed):
        rule = baseline_by_id[rule_id]
        if rule.effect is DecisionEffect.ALLOW:
            continue
        findings.append(
            _finding(
                kind=AuthorityFindingKind.POTENTIAL_EXPANSION,
                code="rule_removed",
                before=rule,
                after=None,
                before_pos=baseline_pos[rule_id],
                after_pos=None,
                relation=None,
                message=(
                    f"Candidate removes {rule.effect.value} rule {rule_id!r}; "
                    "requests previously stopped by it can fall through to a more-permissive decision."
                ),
            )
        )

    reorder = _reorder_finding(baseline, candidate, shared, renames)
    if reorder is not None:
        findings.append(reorder)

    if _EFFECT_RANK[candidate.default_effect] > _EFFECT_RANK[baseline.default_effect]:
        findings.append(
            _finding(
                kind=AuthorityFindingKind.POTENTIAL_EXPANSION,
                code="default_effect_relaxed",
                before=None,
                after=None,
                before_pos=None,
                after_pos=None,
                relation=None,
                before_effect=baseline.default_effect,
                after_effect=candidate.default_effect,
                extra={
                    "baseline_default_effect": baseline.default_effect.value,
                    "candidate_default_effect": candidate.default_effect.value,
                },
                message=(
                    f"Default effect relaxed from {baseline.default_effect.value} "
                    f"to {candidate.default_effect.value}."
                ),
            )
        )

    return sorted(findings, key=lambda item: (item.code, item.fingerprint))


def match_relation(baseline: RuleMatch, candidate: RuleMatch) -> MatchRelation:
    """Compare match-set containment for a deliberately bounded semantic subset."""

    relations = [
        *[
            _glob_relation(getattr(baseline, name), getattr(candidate, name))
            for name in _GLOB_FIELDS
        ],
        _finite_set_relation(baseline.risks, candidate.risks, empty_means_universal=True),
        *[
            _optional_bool_relation(getattr(baseline, name), getattr(candidate, name))
            for name in _BOOL_FIELDS
        ],
        _predicate_relation(baseline.arguments, candidate.arguments),
    ]
    material = {item for item in relations if item is not MatchRelation.EQUAL}
    if not material:
        return MatchRelation.EQUAL
    if MatchRelation.UNKNOWN in material:
        return MatchRelation.UNKNOWN
    if MatchRelation.INCOMPARABLE in material:
        return MatchRelation.INCOMPARABLE
    if material == {MatchRelation.BROADER}:
        return MatchRelation.BROADER
    if material == {MatchRelation.NARROWER}:
        return MatchRelation.NARROWER
    return MatchRelation.INCOMPARABLE


def _classify_rule_change(
    before: DecisionEffect,
    after: DecisionEffect,
    relation: MatchRelation,
) -> AuthorityFindingKind | None:
    if before is after:
        if relation is MatchRelation.EQUAL:
            return None
        if before is DecisionEffect.ALLOW:
            if relation is MatchRelation.BROADER:
                return AuthorityFindingKind.POTENTIAL_EXPANSION
            if relation is MatchRelation.NARROWER:
                return None
            return AuthorityFindingKind.UNKNOWN
        if before is DecisionEffect.DENY:
            if relation is MatchRelation.NARROWER:
                return AuthorityFindingKind.POTENTIAL_EXPANSION
            if relation is MatchRelation.BROADER:
                return None
            return AuthorityFindingKind.UNKNOWN
        return AuthorityFindingKind.UNKNOWN

    if _EFFECT_RANK[after] > _EFFECT_RANK[before]:
        if relation in {MatchRelation.EQUAL, MatchRelation.BROADER, MatchRelation.NARROWER}:
            return AuthorityFindingKind.POTENTIAL_EXPANSION
        return AuthorityFindingKind.UNKNOWN

    if before is DecisionEffect.ALLOW and after is DecisionEffect.DENY:
        return None
    if (
        before is DecisionEffect.ALLOW
        and after is DecisionEffect.REQUIRE_APPROVAL
        and relation in {MatchRelation.EQUAL, MatchRelation.NARROWER}
    ):
        return None
    if (
        before is DecisionEffect.REQUIRE_APPROVAL
        and after is DecisionEffect.DENY
        and relation in {MatchRelation.EQUAL, MatchRelation.BROADER}
    ):
        return None
    return AuthorityFindingKind.UNKNOWN


def _rule_change_code(
    before: DecisionEffect,
    after: DecisionEffect,
    relation: MatchRelation,
) -> str:
    if before is not after and relation is not MatchRelation.EQUAL:
        return "rule_effect_and_scope_changed"
    if before is not after:
        return "rule_effect_changed"
    if relation is MatchRelation.BROADER:
        return "rule_scope_broadened"
    if relation is MatchRelation.NARROWER:
        return "rule_scope_narrowed"
    return "rule_scope_change_unproven"


def _rule_change_message(
    rule_id: str,
    before: DecisionEffect,
    after: DecisionEffect,
    relation: MatchRelation,
    kind: AuthorityFindingKind,
) -> str:
    effect = "" if before is after else f" effect {before.value} → {after.value};"
    conclusion = (
        " this change can increase effective authority outside observed scenarios."
        if kind is AuthorityFindingKind.POTENTIAL_EXPANSION
        else " PermitDiff cannot prove this change non-expanding with its bounded static model."
    )
    return f"Rule {rule_id!r}:{effect} candidate match relation is {relation.value};{conclusion}"


def _same_position_renames(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    removed: set[str],
    added: set[str],
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for before, after in zip(baseline.rules, candidate.rules, strict=False):
        if (
            before.id in removed
            and after.id in added
            and semantic_rule_payload(before) == semantic_rule_payload(after)
        ):
            pairs.add((before.id, after.id))
    return pairs


def _reorder_finding(
    baseline: PolicyDocument,
    candidate: PolicyDocument,
    shared: set[str],
    renames: set[tuple[str, str]],
) -> AuthorityFinding | None:
    rename_map = dict(renames)
    before_order = [
        rename_map.get(rule.id, rule.id)
        for rule in baseline.rules
        if rule.id in shared or rule.id in rename_map
    ]
    tracked = shared | set(rename_map.values())
    after_order = [rule.id for rule in candidate.rules if rule.id in tracked]
    if before_order == after_order:
        return None

    before_index = {rule_id: index for index, rule_id in enumerate(before_order)}
    after_index = {rule_id: index for index, rule_id in enumerate(after_order)}
    before_rules = {rename_map.get(rule.id, rule.id): rule for rule in baseline.rules}
    after_rules = {rule.id: rule for rule in candidate.rules}
    ordered = sorted(set(before_index) & set(after_index), key=before_index.__getitem__)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if after_index[left] < after_index[right]:
                continue
            if (
                before_rules[left].effect is before_rules[right].effect
                is after_rules[left].effect is after_rules[right].effect
            ):
                continue
            return _finding(
                kind=AuthorityFindingKind.UNKNOWN,
                code="rule_order_changed",
                before=None,
                after=None,
                before_pos=None,
                after_pos=None,
                relation=None,
                extra={"baseline_order": before_order, "candidate_order": after_order},
                message=(
                    "Rules with different effects changed precedence; PermitDiff cannot prove "
                    "the reordered first-match policy non-expanding."
                ),
            )
    return None


def _finding(
    *,
    kind: AuthorityFindingKind,
    code: str,
    before: PolicyRule | None,
    after: PolicyRule | None,
    before_pos: int | None,
    after_pos: int | None,
    relation: MatchRelation | None,
    message: str,
    before_effect: DecisionEffect | None = None,
    after_effect: DecisionEffect | None = None,
    extra: dict[str, Any] | None = None,
) -> AuthorityFinding:
    resolved_before = before.effect if before is not None else before_effect
    resolved_after = after.effect if after is not None else after_effect
    payload = {
        "code": code,
        "kind": kind.value,
        "baseline_rule_id": before.id if before is not None else None,
        "candidate_rule_id": after.id if after is not None else None,
        "baseline_position": before_pos,
        "candidate_position": after_pos,
        "baseline_rule": semantic_rule_payload(before) if before is not None else None,
        "candidate_rule": semantic_rule_payload(after) if after is not None else None,
        "baseline_effect": resolved_before.value if resolved_before is not None else None,
        "candidate_effect": resolved_after.value if resolved_after is not None else None,
        "match_relation": relation.value if relation is not None else None,
        "extra": extra,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return AuthorityFinding(
        fingerprint=fingerprint,
        kind=kind,
        code=code,
        baseline_rule_id=before.id if before is not None else None,
        candidate_rule_id=after.id if after is not None else None,
        baseline_effect=resolved_before,
        candidate_effect=resolved_after,
        match_relation=relation,
        message=message,
    )


def _glob_relation(baseline: list[str], candidate: list[str]) -> MatchRelation:
    before = {"*"} if "*" in baseline else set(baseline)
    after = {"*"} if "*" in candidate else set(candidate)
    if before == after:
        return MatchRelation.EQUAL
    if after == {"*"}:
        return MatchRelation.BROADER
    if before == {"*"}:
        return MatchRelation.NARROWER
    if all(not _glob_meta(item) for item in before | after):
        return _finite_set_relation(before, after)

    if all(not _glob_meta(item) for item in before):
        if all(any(fnmatchcase(value, pattern) for pattern in after) for value in before):
            return MatchRelation.BROADER if _glob_has_extra_witness(after, before) else MatchRelation.UNKNOWN
    if all(not _glob_meta(item) for item in after):
        if all(any(fnmatchcase(value, pattern) for pattern in before) for value in after):
            return MatchRelation.NARROWER if _glob_has_extra_witness(before, after) else MatchRelation.UNKNOWN
    return MatchRelation.UNKNOWN


def _glob_meta(value: str) -> bool:
    return any(character in value for character in "*?[")


def _glob_has_extra_witness(patterns: set[str], literals: set[str]) -> bool:
    for pattern in patterns:
        if "[" in pattern or not any(character in pattern for character in "*?"):
            continue
        for token in ("__permitdiff_witness__", "x", "zz"):
            witness = pattern.replace("*", token).replace("?", "x")
            if fnmatchcase(witness, pattern) and witness not in literals:
                return True
    return False


def _finite_set_relation(
    baseline: Any,
    candidate: Any,
    *,
    empty_means_universal: bool = False,
) -> MatchRelation:
    before = set(baseline)
    after = set(candidate)
    if before == after:
        return MatchRelation.EQUAL
    if empty_means_universal:
        if not after:
            return MatchRelation.BROADER
        if not before:
            return MatchRelation.NARROWER
    if before < after:
        return MatchRelation.BROADER
    if after < before:
        return MatchRelation.NARROWER
    return MatchRelation.INCOMPARABLE


def _optional_bool_relation(baseline: bool | None, candidate: bool | None) -> MatchRelation:
    if baseline is candidate:
        return MatchRelation.EQUAL
    if candidate is None:
        return MatchRelation.BROADER
    if baseline is None:
        return MatchRelation.NARROWER
    return MatchRelation.INCOMPARABLE


def _predicate_relation(
    baseline: list[Predicate],
    candidate: list[Predicate],
) -> MatchRelation:
    before = {_predicate_key(item): item for item in baseline}
    after = {_predicate_key(item): item for item in candidate}
    before_keys, after_keys = set(before), set(after)
    if before_keys == after_keys:
        return MatchRelation.EQUAL
    if after_keys < before_keys:
        return MatchRelation.BROADER
    if before_keys < after_keys:
        return MatchRelation.NARROWER

    before_only = [before[key] for key in before_keys - after_keys]
    after_only = [after[key] for key in after_keys - before_keys]
    if len(before_only) == len(after_only) == 1:
        return _changed_predicate_relation(before_only[0], after_only[0])
    return MatchRelation.UNKNOWN


def _predicate_key(predicate: Predicate) -> str:
    return json.dumps(
        predicate.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _changed_predicate_relation(before: Predicate, after: Predicate) -> MatchRelation:
    if before.path != after.path:
        return MatchRelation.UNKNOWN

    upper = {"less_than": False, "less_than_or_equal": True}
    lower = {"greater_than": False, "greater_than_or_equal": True}
    if before.operator in upper and after.operator in upper:
        return _numeric_bound_relation(before, after, upper, upper_bound=True)
    if before.operator in lower and after.operator in lower:
        return _numeric_bound_relation(before, after, lower, upper_bound=False)
    if before.operator == after.operator == "matches":
        before_patterns = [before.value] if isinstance(before.value, str) else before.value
        after_patterns = [after.value] if isinstance(after.value, str) else after.value
        if isinstance(before_patterns, list) and isinstance(after_patterns, list):
            return _glob_relation(before_patterns, after_patterns)
    if before.operator == after.operator == "in":
        relation = _json_list_relation(before.value, after.value)
        if relation is not None:
            return relation
    if before.operator == after.operator == "not_in":
        relation = _json_list_relation(before.value, after.value)
        if relation is not None:
            if relation is MatchRelation.BROADER:
                return MatchRelation.NARROWER
            if relation is MatchRelation.NARROWER:
                return MatchRelation.BROADER
            return relation
    return MatchRelation.UNKNOWN


def _json_list_relation(baseline: Any, candidate: Any) -> MatchRelation | None:
    if not isinstance(baseline, list) or not isinstance(candidate, list):
        return None
    try:
        before = {
            json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for item in baseline
        }
        after = {
            json.dumps(item, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for item in candidate
        }
    except (TypeError, ValueError):
        return None
    return _finite_set_relation(before, after)


def _numeric_bound_relation(
    before: Predicate,
    after: Predicate,
    inclusive: dict[str, bool],
    *,
    upper_bound: bool,
) -> MatchRelation:
    if not _number(before.value) or not _number(after.value):
        return MatchRelation.UNKNOWN
    if before.value == after.value:
        if inclusive[before.operator] == inclusive[after.operator]:
            return MatchRelation.EQUAL
        candidate_is_broader = inclusive[after.operator]
    else:
        candidate_is_broader = after.value > before.value if upper_bound else after.value < before.value
    return MatchRelation.BROADER if candidate_is_broader else MatchRelation.NARROWER


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
