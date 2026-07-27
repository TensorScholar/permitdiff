from __future__ import annotations

from permitdiff.engine import PolicyEngine
from permitdiff.models import ActionContext, ActionRequest, DecisionEffect, ToolAnnotations
from permitdiff.policy import PolicyDocument


def _find(scenarios: list, scenario_id: str):
    return next(item for item in scenarios if item.id == scenario_id)


def test_baseline_allows_trusted_read(baseline: PolicyDocument, scenarios: list) -> None:
    decision = PolicyEngine(baseline).evaluate(_find(scenarios, "customer-read").action)
    assert decision.effect is DecisionEffect.ALLOW
    assert decision.rule_id == "allow-trusted-bounded-reads"


def test_baseline_requires_refund_approval(baseline: PolicyDocument, scenarios: list) -> None:
    decision = PolicyEngine(baseline).evaluate(_find(scenarios, "refund-50").action)
    assert decision.effect is DecisionEffect.REQUIRE_APPROVAL


def test_candidate_allows_low_refund(candidate: PolicyDocument, scenarios: list) -> None:
    decision = PolicyEngine(candidate).evaluate(_find(scenarios, "refund-50").action)
    assert decision.effect is DecisionEffect.ALLOW
    assert decision.rule_id == "allow-low-value-refunds"


def test_first_match_preserves_large_transfer_deny(
    candidate: PolicyDocument,
    scenarios: list,
) -> None:
    decision = PolicyEngine(candidate).evaluate(_find(scenarios, "transfer-20000").action)
    assert decision.effect is DecisionEffect.DENY
    assert decision.rule_id == "deny-large-transfers"


def test_unknown_tool_uses_default_deny(baseline: PolicyDocument, scenarios: list) -> None:
    decision = PolicyEngine(baseline).evaluate(_find(scenarios, "unknown-tool").action)
    assert decision.effect is DecisionEffect.DENY
    assert decision.rule_id is None


def test_untrusted_metadata_cannot_authorize_read(baseline: PolicyDocument) -> None:
    request = ActionRequest(
        principal="p",
        agent="a",
        tool="crm.lookup_customer",
        annotations=ToolAnnotations(read_only=True, open_world=False),
        context=ActionContext(security_metadata_trusted=False),
    )
    assert PolicyEngine(baseline).evaluate(request).effect is DecisionEffect.DENY


def test_untrusted_destructive_hint_can_trigger_restriction(baseline: PolicyDocument) -> None:
    request = ActionRequest(
        principal="p",
        agent="a",
        tool="unknown",
        annotations=ToolAnnotations(destructive=True),
        context=ActionContext(security_metadata_trusted=False),
    )
    assert PolicyEngine(baseline).evaluate(request).effect is DecisionEffect.REQUIRE_APPROVAL


def test_policy_digest_is_attached(baseline: PolicyDocument, scenarios: list) -> None:
    decision = PolicyEngine(baseline).evaluate(_find(scenarios, "customer-read").action)
    assert decision.policy_digest == baseline.digest()
