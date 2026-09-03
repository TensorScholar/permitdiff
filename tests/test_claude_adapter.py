from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from permitdiff.adapters.claude_code import ClaudeAdapterError, normalize_claude_preapproval_pair
from permitdiff.analysis import compare_policies
from permitdiff.corpus import load_corpus

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "validation/public-claude-permission-widening"


def _settings(
    tmp_path: Path,
    name: str,
    *,
    allow: list[str],
    deny: list[str] | None = None,
    ask: list[str] | None = None,
    default_mode: str = "dontAsk",
    root: dict[str, Any] | None = None,
) -> Path:
    path = tmp_path / name
    document: dict[str, Any] = {
        "permissions": {
            "allow": allow,
            "deny": deny or [],
            "ask": ask or [],
            "defaultMode": default_mode,
        }
    }
    document.update(root or {})
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_public_claude_pilot_normalizes_to_two_preapproval_expansions() -> None:
    pair = normalize_claude_preapproval_pair(
        PILOT / "source-baseline.json",
        PILOT / "source-candidate.json",
        allow_ignored_root_changes=True,
        acknowledge_webfetch_sandbox_gap=True,
    )
    report = compare_policies(
        pair.baseline_policy,
        pair.candidate_policy,
        load_corpus(PILOT / "corpus.jsonl"),
    )

    assert report.summary.changed_effects == 2
    assert report.summary.privilege_expansions == 2
    assert report.summary.new_allows == 2
    assert report.summary.approval_bypasses == 0
    assert report.summary.static_authority_expansions == 2
    assert report.summary.static_authority_unknowns == 0
    assert pair.evidence.shared_opaque_allow_rules == ["Read(**)"]
    assert pair.evidence.candidate_redundant_allow_rules == ["Bash(git mv *)"]
    assert set(pair.evidence.candidate_translated_allow_rules) - set(
        pair.evidence.baseline_translated_allow_rules
    ) == {"WebSearch", "WebFetch(domain:www.anthropic.com)"}
    assert pair.evidence.ignored_baseline_root_keys == ["enabledPlugins"]
    assert pair.evidence.ignored_candidate_root_keys == ["enabledPlugins"]
    assert pair.evidence.changed_ignored_root_keys == ["enabledPlugins"]
    assert pair.evidence.ignored_root_changes_acknowledged is True
    assert pair.evidence.webfetch_sandbox_gap_acknowledged is True
    assert report.candidate_coverage.uncovered_rules == []


def test_same_effect_bare_tool_eliminates_scoped_redundancy(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=["Bash"])
    candidate = _settings(tmp_path, "candidate.json", allow=["Bash", "Bash(git mv *)"])

    pair = normalize_claude_preapproval_pair(baseline, candidate)

    assert pair.baseline_policy.rules == pair.candidate_policy.rules
    assert pair.evidence.candidate_redundant_allow_rules == ["Bash(git mv *)"]


def test_read_star_is_not_treated_as_bare_read(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=[])
    candidate = _settings(tmp_path, "candidate.json", allow=["Read(*)"])

    with pytest.raises(ClaudeAdapterError, match="unsupported Claude allow rules changed"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_webfetch_domain_star_is_not_treated_as_bare_webfetch(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=[])
    candidate = _settings(tmp_path, "candidate.json", allow=["WebFetch(domain:*)"])

    with pytest.raises(ClaudeAdapterError, match="unsupported Claude allow rules changed"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_unchanged_webfetch_domain_star_is_carried_as_opaque_evidence(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=["WebFetch(domain:*)"])
    candidate = _settings(tmp_path, "candidate.json", allow=["WebFetch(domain:*)"])

    pair = normalize_claude_preapproval_pair(baseline, candidate)

    assert pair.baseline_policy.rules == []
    assert pair.candidate_policy.rules == []
    assert pair.evidence.shared_opaque_allow_rules == ["WebFetch(domain:*)"]


def test_changed_unsupported_allow_rules_fail_closed(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=["Read(**)"])
    candidate = _settings(tmp_path, "candidate.json", allow=["Read(src/**)"])

    with pytest.raises(ClaudeAdapterError, match="unsupported Claude allow rules changed"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_changed_deny_or_ask_context_fails_closed(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=["WebSearch"], deny=["Bash(rm *)"])
    candidate = _settings(tmp_path, "candidate.json", allow=["WebSearch"], deny=[])

    with pytest.raises(ClaudeAdapterError, match="deny and ask rules to remain unchanged"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_changed_allow_shadowed_by_unchanged_restrictive_rule_fails_closed(
    tmp_path: Path,
) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=[], deny=["WebSearch"])
    candidate = _settings(tmp_path, "candidate.json", allow=["WebSearch"], deny=["WebSearch"])

    with pytest.raises(ClaudeAdapterError, match="overlap unchanged deny/ask"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_webfetch_domain_change_requires_explicit_sandbox_gap_acknowledgement(
    tmp_path: Path,
) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=[])
    candidate = _settings(
        tmp_path,
        "candidate.json",
        allow=["WebFetch(domain:WWW.Anthropic.COM.)"],
    )

    with pytest.raises(ClaudeAdapterError, match="explicit WebFetch sandbox-gap acknowledgement"):
        normalize_claude_preapproval_pair(baseline, candidate)

    pair = normalize_claude_preapproval_pair(
        baseline,
        candidate,
        acknowledge_webfetch_sandbox_gap=True,
    )
    rule = pair.candidate_policy.rules[0]

    assert rule.id == "claude-allow-webfetch-domains"
    assert rule.match.arguments[0].value == ["www.anthropic.com"]
    assert pair.evidence.webfetch_sandbox_gap_acknowledged is True


def test_non_permission_root_changes_require_explicit_acknowledgement(tmp_path: Path) -> None:
    baseline = _settings(
        tmp_path,
        "baseline.json",
        allow=["WebSearch"],
        root={"enabledPlugins": {"one@example": True}, "model": "sonnet"},
    )
    candidate = _settings(
        tmp_path,
        "candidate.json",
        allow=["WebSearch"],
        root={
            "enabledPlugins": {"one@example": True, "two@example": True},
            "model": "sonnet",
        },
    )

    with pytest.raises(ClaudeAdapterError, match="non-permissions Claude root settings changed"):
        normalize_claude_preapproval_pair(baseline, candidate)

    pair = normalize_claude_preapproval_pair(
        baseline,
        candidate,
        allow_ignored_root_changes=True,
    )

    assert pair.baseline_policy.rules == pair.candidate_policy.rules
    assert pair.evidence.ignored_baseline_root_keys == ["enabledPlugins", "model"]
    assert pair.evidence.ignored_candidate_root_keys == ["enabledPlugins", "model"]
    assert pair.evidence.changed_ignored_root_keys == ["enabledPlugins"]
    assert pair.evidence.ignored_root_changes_acknowledged is True
    assert pair.evidence.webfetch_sandbox_gap_acknowledged is False


def test_unsupported_permission_mode_is_rejected(tmp_path: Path) -> None:
    baseline = _settings(tmp_path, "baseline.json", allow=[], default_mode="default")
    candidate = _settings(tmp_path, "candidate.json", allow=[], default_mode="default")

    with pytest.raises(ClaudeAdapterError, match="supports only explicit defaultMode='dontAsk'"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"permissions":{"allow":[],"allow":["Bash"],"defaultMode":"dontAsk"}}',
        encoding="utf-8",
    )
    candidate = _settings(tmp_path, "candidate.json", allow=[])

    with pytest.raises(ClaudeAdapterError, match="duplicate JSON key"):
        normalize_claude_preapproval_pair(baseline, candidate)


def test_unknown_permission_keys_are_rejected(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "permissions": {
                    "allow": [],
                    "defaultMode": "dontAsk",
                    "futureSemanticSwitch": True,
                }
            }
        ),
        encoding="utf-8",
    )
    candidate = _settings(tmp_path, "candidate.json", allow=[])

    with pytest.raises(ClaudeAdapterError, match="unsupported keys inside Claude permissions"):
        normalize_claude_preapproval_pair(baseline, candidate)
