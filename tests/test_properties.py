from __future__ import annotations

import random

from permitdiff.analysis import compare_policies
from permitdiff.gate import evaluate_gate, strict_gate
from permitdiff.models import ActionRequest, RiskLevel, Scenario
from permitdiff.policy import PolicyDocument


def _policy(effect: str) -> PolicyDocument:
    return PolicyDocument.model_validate(
        {
            "api_version": "permitdiff.dev/v1alpha1",
            "kind": "Policy",
            "metadata": {"name": "property-policy", "version": "1"},
            "default_effect": effect,
            "rules": [],
        }
    )


def test_same_policy_never_creates_an_expansion() -> None:
    rng = random.Random(20260727)
    effects = ["deny", "require_approval", "allow"]
    for index in range(100):
        policy = _policy(rng.choice(effects))
        scenario = Scenario(
            id=f"case-{index}",
            risk=RiskLevel(rng.choice(["low", "medium", "high", "critical"])),
            action=ActionRequest(
                principal="role:test",
                agent="agent:test",
                tool=f"tool.{rng.randrange(8)}",
                arguments={"amount": rng.randrange(10_000)},
            ),
        )
        report = compare_policies(policy, policy, [scenario])
        assert report.summary.privilege_expansions == 0
        assert evaluate_gate(report, strict_gate()).passed


def test_semantic_digests_ignore_request_identity_and_time() -> None:
    first = ActionRequest(
        request_id="one",
        principal="role:test",
        agent="agent:test",
        tool="files.read",
        arguments={"path": "report.pdf"},
    )
    second = first.model_copy(update={"request_id": "two"})
    assert first.fingerprint() == second.fingerprint()
