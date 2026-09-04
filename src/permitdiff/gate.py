"""Release gate configuration, time-bounded waivers, and evaluation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from permitdiff.analysis import ComparisonReport
from permitdiff.authority import AuthorityFinding, AuthorityFindingKind
from permitdiff.errors import GateLoadError
from permitdiff.models import DecisionEffect
from permitdiff.yaml_utils import safe_load_yaml

_MAX_GATE_BYTES = 1_000_000
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class TransitionWaiver(BaseModel):
    """Review evidence for one exact, temporary observed permission transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    scenario_id: str = Field(min_length=1, max_length=256)
    from_effect: DecisionEffect
    to_effect: DecisionEffect
    action_fingerprint: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    baseline_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    candidate_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    reason: str = Field(min_length=10, max_length=2000)
    expires_on: date
    issue: HttpUrl | None = None


class AuthorityWaiver(BaseModel):
    """Review evidence for one exact, temporary static authority finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    finding_kind: AuthorityFindingKind
    finding_fingerprint: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    baseline_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    candidate_digest: str = Field(min_length=64, max_length=64, pattern=_SHA256_PATTERN)
    reason: str = Field(min_length=10, max_length=2000)
    expires_on: date
    issue: HttpUrl | None = None


class GateConfig(BaseModel):
    """Thresholds that convert a comparison report into a release decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: Literal["permitdiff.dev/v1alpha1"] = "permitdiff.dev/v1alpha1"
    kind: Literal["Gate"] = "Gate"
    max_privilege_expansions: int = Field(default=0, ge=0)
    max_new_allows: int = Field(default=0, ge=0)
    max_approval_bypasses: int = Field(default=0, ge=0)
    max_static_authority_expansions: int = Field(default=0, ge=0)
    max_uncovered_candidate_rules: int | None = Field(default=0, ge=0)
    forbid_default_effect_relaxation: bool = True
    forbid_missing_differential_evidence: bool = False
    fail_on_removed_rules: bool = False
    fail_on_unused_waivers: bool = False
    waivers: list[TransitionWaiver] = Field(default_factory=list)
    authority_waivers: list[AuthorityWaiver] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_waivers(self) -> GateConfig:
        all_ids = [item.id for item in self.waivers] + [item.id for item in self.authority_waivers]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("waiver ids must be unique")
        transitions = [
            (
                item.scenario_id,
                item.from_effect,
                item.to_effect,
                item.action_fingerprint,
                item.baseline_digest,
                item.candidate_digest,
            )
            for item in self.waivers
        ]
        if len(transitions) != len(set(transitions)):
            raise ValueError("waivers must target unique scenario transitions")
        findings = [
            (
                item.finding_kind,
                item.finding_fingerprint,
                item.baseline_digest,
                item.candidate_digest,
            )
            for item in self.authority_waivers
        ]
        if len(findings) != len(set(findings)):
            raise ValueError("authority waivers must target unique static findings")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> GateConfig:
        gate_path = Path(path)
        try:
            if gate_path.stat().st_size > _MAX_GATE_BYTES:
                raise ValueError(f"gate exceeds {_MAX_GATE_BYTES} bytes")
            raw = safe_load_yaml(gate_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("gate root must be a mapping")
            return cls.model_validate(raw)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise GateLoadError(f"failed to load gate {gate_path}: {exc}") from exc


class GateViolation(BaseModel):
    """One failed release condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str
    actual: int | str | bool
    limit: int | str | bool


class GateResult(BaseModel):
    """Machine-readable release verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "permitdiff.gate-result/v1alpha1"
    passed: bool
    violations: list[GateViolation]
    waived_scenarios: list[str]
    waived_authority_findings: list[str] = Field(default_factory=list)
    missing_differential_evidence: list[str] = Field(default_factory=list)
    expired_waivers: list[str]
    unused_waivers: list[str]


def evaluate_gate(
    report: ComparisonReport,
    config: GateConfig,
    *,
    today: date | None = None,
) -> GateResult:
    """Apply thresholds after exact, non-expired transition and authority waivers."""

    resolved_today = today or datetime.now(UTC).date()
    active_transition_waivers = [
        item for item in config.waivers if item.expires_on >= resolved_today
    ]
    active_authority_waivers = [
        item for item in config.authority_waivers if item.expires_on >= resolved_today
    ]
    expired = sorted(
        [item.id for item in config.waivers if item.expires_on < resolved_today]
        + [item.id for item in config.authority_waivers if item.expires_on < resolved_today]
    )
    used_waivers: set[str] = set()
    waived_scenarios: set[str] = set()
    waived_authority_findings: set[str] = set()
    unwaived_transitions = []

    for transition in report.transitions:
        matching_transition = next(
            (
                waiver
                for waiver in active_transition_waivers
                if waiver.scenario_id == transition.scenario_id
                and waiver.from_effect is transition.baseline_effect
                and waiver.to_effect is transition.candidate_effect
                and waiver.action_fingerprint == transition.action_fingerprint
                and waiver.baseline_digest == report.baseline_digest
                and waiver.candidate_digest == report.candidate_digest
            ),
            None,
        )
        if matching_transition is not None and transition.privilege_expansion:
            used_waivers.add(matching_transition.id)
            waived_scenarios.add(transition.scenario_id)
        else:
            unwaived_transitions.append(transition)

    unwaived_authority_findings = []
    for finding in report.authority_findings:
        matching_authority = next(
            (
                waiver
                for waiver in active_authority_waivers
                if waiver.finding_kind is finding.kind
                and waiver.finding_fingerprint == finding.fingerprint
                and waiver.baseline_digest == report.baseline_digest
                and waiver.candidate_digest == report.candidate_digest
            ),
            None,
        )
        if matching_authority is not None:
            used_waivers.add(matching_authority.id)
            waived_authority_findings.add(finding.fingerprint)
        else:
            unwaived_authority_findings.append(finding)

    expansions = sum(item.privilege_expansion for item in unwaived_transitions)
    new_allows = sum(item.new_allow for item in unwaived_transitions)
    approval_bypasses = sum(item.approval_bypass for item in unwaived_transitions)
    static_expansions = sum(
        item.kind is AuthorityFindingKind.POTENTIAL_EXPANSION
        for item in unwaived_authority_findings
    )
    static_unknowns = sum(
        item.kind is AuthorityFindingKind.UNKNOWN for item in unwaived_authority_findings
    )
    violations: list[GateViolation] = []
    _append_threshold(
        violations,
        "privilege_expansions",
        expansions,
        config.max_privilege_expansions,
        "unwaived privilege expansions",
    )
    _append_threshold(
        violations,
        "new_allows",
        new_allows,
        config.max_new_allows,
        "unwaived transitions to allow",
    )
    _append_threshold(
        violations,
        "approval_bypasses",
        approval_bypasses,
        config.max_approval_bypasses,
        "unwaived approval-to-allow transitions",
    )
    _append_threshold(
        violations,
        "static_authority_expansions",
        static_expansions,
        config.max_static_authority_expansions,
        "unwaived static authority expansions",
    )
    if static_unknowns:
        violations.append(
            GateViolation(
                code="static_authority_unknown",
                message=(
                    "bounded static analysis cannot prove one or more policy changes non-expanding"
                ),
                actual=static_unknowns,
                limit=0,
            )
        )

    missing_evidence = _missing_differential_evidence(report, unwaived_authority_findings)
    if config.forbid_missing_differential_evidence and missing_evidence:
        violations.append(
            GateViolation(
                code="missing_differential_evidence",
                message=(
                    "static authority expansions without observed differential "
                    "corpus evidence exceed the gate"
                ),
                actual=len(missing_evidence),
                limit=0,
            )
        )

    uncovered = len(report.candidate_coverage.uncovered_rules)
    if (
        config.max_uncovered_candidate_rules is not None
        and uncovered > config.max_uncovered_candidate_rules
    ):
        violations.append(
            GateViolation(
                code="uncovered_candidate_rules",
                message="candidate rules without observed corpus coverage exceed the gate",
                actual=uncovered,
                limit=config.max_uncovered_candidate_rules,
            )
        )

    effect_rank = {
        DecisionEffect.DENY: 0,
        DecisionEffect.REQUIRE_APPROVAL: 1,
        DecisionEffect.ALLOW: 2,
    }
    default_relaxed = (
        effect_rank[report.structural_diff.candidate_default_effect]
        > effect_rank[report.structural_diff.baseline_default_effect]
    )
    if config.forbid_default_effect_relaxation and default_relaxed:
        violations.append(
            GateViolation(
                code="default_effect_relaxation",
                message="candidate default effect is more permissive than the baseline",
                actual=True,
                limit=False,
            )
        )

    if config.fail_on_removed_rules and report.structural_diff.removed_rules:
        violations.append(
            GateViolation(
                code="removed_rules",
                message="candidate policy removes rules while the gate forbids removals",
                actual=len(report.structural_diff.removed_rules),
                limit=0,
            )
        )

    unused = sorted(
        [item.id for item in active_transition_waivers if item.id not in used_waivers]
        + [item.id for item in active_authority_waivers if item.id not in used_waivers]
    )
    if config.fail_on_unused_waivers and unused:
        violations.append(
            GateViolation(
                code="unused_waivers",
                message="active waivers do not match any gate-relevant authority expansion",
                actual=len(unused),
                limit=0,
            )
        )

    return GateResult(
        passed=not violations,
        violations=violations,
        waived_scenarios=sorted(waived_scenarios),
        waived_authority_findings=sorted(waived_authority_findings),
        missing_differential_evidence=missing_evidence,
        expired_waivers=expired,
        unused_waivers=unused,
    )


def strict_gate() -> GateConfig:
    """Return a zero-expansion, fail-closed, full-candidate-coverage release gate."""

    return GateConfig(forbid_missing_differential_evidence=True)


def _missing_differential_evidence(
    report: ComparisonReport,
    unwaived_authority_findings: list[AuthorityFinding],
) -> list[str]:
    """Return fingerprints of unwaived expansions without observed differential evidence.

    A static potential expansion is demonstrated only by an observed privilege
    expansion routed through the changed rule: via the candidate rule for added
    or broadened authority, via the baseline rule for removed or narrowed
    authority, or via the default decision for a relaxed default effect.
    Waivers never remove report evidence, so demonstration is read from all
    report transitions rather than only unwaived ones.
    """

    candidate_demonstrated = {
        transition.candidate_rule_id
        for transition in report.transitions
        if transition.privilege_expansion and transition.candidate_rule_id is not None
    }
    baseline_demonstrated = {
        transition.baseline_rule_id
        for transition in report.transitions
        if transition.privilege_expansion and transition.baseline_rule_id is not None
    }
    default_demonstrated = any(
        transition.privilege_expansion and transition.candidate_rule_id is None
        for transition in report.transitions
    )
    missing: list[str] = []
    for finding in unwaived_authority_findings:
        if finding.kind is not AuthorityFindingKind.POTENTIAL_EXPANSION:
            continue
        if finding.candidate_rule_id is None and finding.baseline_rule_id is None:
            demonstrated = default_demonstrated
        else:
            demonstrated = (
                finding.candidate_rule_id is not None
                and finding.candidate_rule_id in candidate_demonstrated
            ) or (
                finding.baseline_rule_id is not None
                and finding.baseline_rule_id in baseline_demonstrated
            )
        if not demonstrated:
            missing.append(finding.fingerprint)
    return sorted(missing)


def _append_threshold(
    violations: list[GateViolation],
    code: str,
    actual: int,
    limit: int,
    label: str,
) -> None:
    if actual > limit:
        violations.append(
            GateViolation(
                code=code,
                message=f"{label} exceed the configured gate",
                actual=actual,
                limit=limit,
            )
        )
