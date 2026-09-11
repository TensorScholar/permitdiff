from __future__ import annotations

from permitdiff.gate import GateConfig, strict_gate


def test_strict_profile_pins_security_relevant_invariants() -> None:
    config = strict_gate()

    assert config.max_privilege_expansions == 0
    assert config.max_new_allows == 0
    assert config.max_approval_bypasses == 0
    assert config.max_static_authority_expansions == 0
    assert config.max_uncovered_candidate_rules == 0
    assert config.forbid_default_effect_relaxation is True
    assert config.forbid_missing_differential_evidence is True
    assert config.waivers == []
    assert config.authority_waivers == []


def test_custom_gate_can_deliberately_disable_candidate_coverage_threshold() -> None:
    config = GateConfig(max_uncovered_candidate_rules=None)

    assert config.max_uncovered_candidate_rules is None


def test_custom_gate_does_not_implicitly_enable_strict_differential_evidence() -> None:
    config = GateConfig()

    assert config.forbid_missing_differential_evidence is False
