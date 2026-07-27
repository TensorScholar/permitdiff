"""Deterministic, ordered permission policy evaluation."""

from __future__ import annotations

from fnmatch import fnmatchcase

from permitdiff.models import ActionRequest, Decision, DecisionEffect, RiskLevel
from permitdiff.policy import PolicyDocument, PolicyRule
from permitdiff.predicates import evaluate_predicate


class PolicyEngine:
    """Evaluate normalized tool calls against an immutable policy document."""

    def __init__(self, policy: PolicyDocument) -> None:
        self._policy = policy
        self._digest = policy.digest()

    @property
    def policy(self) -> PolicyDocument:
        return self._policy

    @property
    def policy_digest(self) -> str:
        return self._digest

    def evaluate(self, request: ActionRequest) -> Decision:
        for rule in self._policy.rules:
            if self._matches(rule, request):
                return Decision(
                    request_id=request.request_id,
                    effect=rule.effect,
                    reason=rule.description,
                    rule_id=rule.id,
                    policy_digest=self._digest,
                    action_fingerprint=request.fingerprint(),
                )

        return Decision(
            request_id=request.request_id,
            effect=self._policy.default_effect,
            reason=f"no rule matched; default effect is {self._policy.default_effect.value}",
            policy_digest=self._digest,
            action_fingerprint=request.fingerprint(),
        )

    def _matches(self, rule: PolicyRule, request: ActionRequest) -> bool:
        match = rule.match
        trusted = request.context.security_metadata_trusted

        uses_security_metadata = bool(match.risks) or any(
            value is not None
            for value in (
                match.read_only,
                match.destructive,
                match.idempotent,
                match.open_world,
            )
        )
        if rule.effect is DecisionEffect.ALLOW and uses_security_metadata and not trusted:
            return False

        risk = (
            request.context.risk
            if trusted and request.context.risk
            else self._infer_risk(request)
        )
        return (
            _matches_any(request.tool, match.tools)
            and _matches_any(request.principal, match.principals)
            and _matches_any(request.agent, match.agents)
            and _matches_any(request.context.environment, match.environments)
            and _matches_any(request.context.source, match.sources)
            and (not match.risks or risk in match.risks)
            and _optional_bool(match.security_metadata_trusted, trusted)
            and _optional_bool(match.read_only, request.annotations.read_only)
            and _optional_bool(match.destructive, request.annotations.destructive)
            and _optional_bool(match.idempotent, request.annotations.idempotent)
            and _optional_bool(match.open_world, request.annotations.open_world)
            and all(evaluate_predicate(item, request.arguments) for item in match.arguments)
        )

    @staticmethod
    def _infer_risk(request: ActionRequest) -> RiskLevel:
        if not request.context.security_metadata_trusted:
            return RiskLevel.HIGH
        annotations = request.annotations
        if annotations.destructive is True:
            return RiskLevel.HIGH
        if annotations.open_world is True and annotations.read_only is not True:
            return RiskLevel.MEDIUM
        if annotations.read_only is True:
            return RiskLevel.LOW
        return RiskLevel.MEDIUM


def _matches_any(value: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(value, pattern) for pattern in patterns)


def _optional_bool(expected: bool | None, actual: bool | None) -> bool:
    return expected is None or actual is expected
