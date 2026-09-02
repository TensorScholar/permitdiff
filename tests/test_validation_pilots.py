from __future__ import annotations

import json
from pathlib import Path

from permitdiff.analysis import compare_policies
from permitdiff.authority import AuthorityFindingKind
from permitdiff.corpus import load_corpus
from permitdiff.gate import GateConfig, evaluate_gate
from permitdiff.models import DecisionEffect
from permitdiff.policy import PolicyDocument

_ROOT = Path(__file__).resolve().parents[1]
_PILOT = _ROOT / "validation" / "agentguard-approval-exception"
_AGENTGUARD_BASELINE = "0b65e4dc7d3069471b005da8d29297586f1d5f64"
_AGENTGUARD_CANDIDATE = "0ebd301db4fcc20c97b0866cd05360ebf3499c7d"


def test_agentguard_scoped_approval_exception_historical_pilot() -> None:
    source = json.loads((_PILOT / "source.json").read_text(encoding="utf-8"))
    assert source["source_repository"] == "TensorScholar/agentguard"
    assert source["baseline_commit"] == _AGENTGUARD_BASELINE
    assert source["candidate_commit"] == _AGENTGUARD_CANDIDATE
    assert source["ground_truth"] == {
        "change": (
            "A matching, non-hard-denied shell_execution approval exception returns ALLOW "
            "where the prior policy path required approval."
        ),
        "tool_pattern": "run_*",
        "required_capability": "shell_execution",
        "baseline_effect": "require_approval",
        "candidate_effect": "allow",
        "hard_denies_precede_exception": True,
    }

    baseline = PolicyDocument.from_yaml(_PILOT / "baseline.yaml")
    candidate = PolicyDocument.from_yaml(_PILOT / "candidate.yaml")
    scenarios = load_corpus(_PILOT / "corpus.jsonl")
    report = compare_policies(baseline, candidate, scenarios)
    transitions = {item.scenario_id: item for item in report.transitions}

    scoped = transitions["scoped-run-status"]
    assert scoped.baseline_effect is DecisionEffect.REQUIRE_APPROVAL
    assert scoped.candidate_effect is DecisionEffect.ALLOW
    assert scoped.privilege_expansion
    assert scoped.new_allow
    assert scoped.approval_bypass

    nonmatching = transitions["nonmatching-shell"]
    assert nonmatching.baseline_effect is DecisionEffect.REQUIRE_APPROVAL
    assert nonmatching.candidate_effect is DecisionEffect.REQUIRE_APPROVAL
    assert not nonmatching.privilege_expansion

    unrelated = transitions["unrelated-read"]
    assert unrelated.baseline_effect is DecisionEffect.DENY
    assert unrelated.candidate_effect is DecisionEffect.DENY
    assert not unrelated.privilege_expansion

    assert report.summary.scenarios == 3
    assert report.summary.changed_effects == 1
    assert report.summary.privilege_expansions == 1
    assert report.summary.new_allows == 1
    assert report.summary.approval_bypasses == 1
    assert report.summary.static_authority_expansions == 1
    assert report.summary.static_authority_unknowns == 0

    assert report.candidate_coverage.uncovered_rules == []
    assert report.candidate_coverage.rule_hits == {
        "scoped-run-shell-exception": 1,
        "shell-execution-requires-approval": 1,
    }
    assert report.candidate_coverage.default_hits == 1

    assert len(report.authority_findings) == 1
    finding = report.authority_findings[0]
    assert finding.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
    assert finding.code == "rule_added"
    assert finding.candidate_rule_id == "scoped-run-shell-exception"

    gate = GateConfig.from_yaml(_PILOT / "gate.yaml")
    result = evaluate_gate(report, gate)
    assert not result.passed
    assert {item.code for item in result.violations} == {
        "privilege_expansions",
        "new_allows",
        "approval_bypasses",
        "static_authority_expansions",
    }
