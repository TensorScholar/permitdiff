from __future__ import annotations

import hashlib
import json
from pathlib import Path

from permitdiff.analysis import compare_policies
from permitdiff.authority import AuthorityFindingKind
from permitdiff.corpus import load_corpus
from permitdiff.gate import GateConfig, evaluate_gate
from permitdiff.models import DecisionEffect
from permitdiff.policy import PolicyDocument

_ROOT = Path(__file__).resolve().parents[1]
_PILOT = _ROOT / "validation" / "public-claude-permission-widening"
_BASELINE_COMMIT = "28133b63a9a54621c8d7be879ba671daf8464c1c"
_BASELINE_BLOB = "87d28d71c3a8b65142e5e090e8deb42130fd3637"
_CANDIDATE_COMMIT = "d8a47de7f5f96d501432a7f02c6909c667a5f31d"
_CANDIDATE_BLOB = "2e5f2bb998c7e5ed4d6394b8934144207546472d"


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode()
    return hashlib.sha1(header + payload, usedforsecurity=False).hexdigest()


def test_public_claude_permission_widening_pilot() -> None:
    source = json.loads((_PILOT / "source.json").read_text(encoding="utf-8"))
    baseline_path = _PILOT / "source-baseline.json"
    candidate_path = _PILOT / "source-candidate.json"
    baseline_source = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate_source = json.loads(candidate_path.read_text(encoding="utf-8"))

    assert source["source_repository"] == "SpearIT-LLC/project-framework"
    assert source["baseline_commit"] == _BASELINE_COMMIT
    assert source["baseline_blob"] == _BASELINE_BLOB
    assert source["candidate_commit"] == _CANDIDATE_COMMIT
    assert source["candidate_blob"] == _CANDIDATE_BLOB
    assert _git_blob_sha(baseline_path) == _BASELINE_BLOB
    assert _git_blob_sha(candidate_path) == _CANDIDATE_BLOB
    assert baseline_source["permissions"]["defaultMode"] == "dontAsk"
    assert candidate_source["permissions"]["defaultMode"] == "dontAsk"
    assert baseline_source["permissions"]["deny"] == candidate_source["permissions"]["deny"]

    baseline_allow = set(baseline_source["permissions"]["allow"])
    candidate_allow = set(candidate_source["permissions"]["allow"])
    added = candidate_allow - baseline_allow
    assert added == {
        "Bash(git mv *)",
        "WebFetch(domain:www.anthropic.com)",
        "WebSearch",
    }
    assert "Bash" in baseline_allow

    baseline_plugins = {
        name for name, enabled in baseline_source["enabledPlugins"].items() if enabled
    }
    candidate_plugins = {
        name for name, enabled in candidate_source["enabledPlugins"].items() if enabled
    }
    assert candidate_plugins - baseline_plugins == {"spearit-framework-dev@dev-marketplace"}
    assert source["source_delta"]["changed_non_permission_root_keys"] == ["enabledPlugins"]
    assert source["source_delta"]["enabled_plugins_added"] == [
        "spearit-framework-dev@dev-marketplace"
    ]

    assert source["normalization"]["modeled_preapproval_expansions"] == [
        "WebFetch(domain:www.anthropic.com)",
        "WebSearch",
    ]
    assert source["normalization"]["redundant_additions"] == ["Bash(git mv *)"]

    baseline = PolicyDocument.from_yaml(_PILOT / "baseline.yaml")
    candidate = PolicyDocument.from_yaml(_PILOT / "candidate.yaml")
    scenarios = load_corpus(_PILOT / "corpus.jsonl")
    report = compare_policies(baseline, candidate, scenarios)
    transitions = {item.scenario_id: item for item in report.transitions}

    redundant = transitions["existing-bash-git-mv"]
    assert redundant.baseline_effect is DecisionEffect.ALLOW
    assert redundant.candidate_effect is DecisionEffect.ALLOW
    assert not redundant.privilege_expansion

    search = transitions["new-websearch"]
    assert search.baseline_effect is DecisionEffect.DENY
    assert search.candidate_effect is DecisionEffect.ALLOW
    assert search.privilege_expansion
    assert search.new_allow

    fetch = transitions["new-anthropic-webfetch"]
    assert fetch.baseline_effect is DecisionEffect.DENY
    assert fetch.candidate_effect is DecisionEffect.ALLOW
    assert fetch.privilege_expansion
    assert fetch.new_allow

    other = transitions["other-domain-webfetch"]
    assert other.baseline_effect is DecisionEffect.DENY
    assert other.candidate_effect is DecisionEffect.DENY
    assert not other.privilege_expansion

    assert report.summary.scenarios == 4
    assert report.summary.changed_effects == 2
    assert report.summary.privilege_expansions == 2
    assert report.summary.new_allows == 2
    assert report.summary.approval_bypasses == 0
    assert report.summary.static_authority_expansions == 2
    assert report.summary.static_authority_unknowns == 0
    assert report.candidate_coverage.uncovered_rules == []
    assert report.candidate_coverage.rule_hits == {
        "websearch-preapproval": 1,
        "anthropic-webfetch-preapproval": 1,
        "existing-tool-preapprovals": 1,
    }
    assert report.candidate_coverage.default_hits == 1

    assert len(report.authority_findings) == 2
    assert all(
        item.kind is AuthorityFindingKind.POTENTIAL_EXPANSION for item in report.authority_findings
    )
    assert {item.candidate_rule_id for item in report.authority_findings} == {
        "websearch-preapproval",
        "anthropic-webfetch-preapproval",
    }

    gate = GateConfig.from_yaml(_PILOT / "gate.yaml")
    result = evaluate_gate(report, gate)
    assert not result.passed
    assert {item.code for item in result.violations} == {
        "privilege_expansions",
        "new_allows",
        "static_authority_expansions",
    }
