"""Release gate configuration, time-bounded waivers, and evaluation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from permitdiff.analysis import ComparisonReport
from permitdiff.errors import GateLoadError
from permitdiff.models import DecisionEffect
from permitdiff.yaml_utils import safe_load_yaml

_MAX_GATE_BYTES = 1_000_000


class TransitionWaiver(BaseModel):
    """Review evidence for one exact, temporary permission transition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    scenario_id: str = Field(min_length=1, max_length=256)
    from_effect: DecisionEffect
    to_effect: DecisionEffect
    action_fingerprint: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
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
    max_uncovered_candidate_rules: int | None = Field(default=0, ge=0)
    forbid_default_effect_relaxation: bool = True
    fail_on_removed_rules: bool = False
    fail_on_unused_waivers: bool = False
    waivers: list[TransitionWaiver] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_waivers(self) -> GateConfig:
        ids = [item.id for item in self.waivers]
        if len(ids) != len(set(ids)):
            raise ValueError("waiver ids must be unique")
        transitions = [
            (
                item.scenario_id,
                item.from_effect,
                item.to_effect,
                item.action_fingerprint,
            )
            for item in self.waivers
        ]
        if len(transitions) != len(set(transitions)):
            raise ValueError("waivers must target unique scenario transitions")
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
    expired_waivers: list[str]
    unused_waivers: list[str]


def evaluate_gate(
    report: ComparisonReport,
    config: GateConfig,
    *,
    today: date | None = None,
) -> GateResult:
    """Apply thresholds after exact, non-expired transition waivers."""

    resolved_today = today or datetime.now(UTC).date()
    active_waivers = [item for item in config.waivers if item.expires_on >= resolved_today]
    expired = sorted(item.id for item in config.waivers if item.expires_on < resolved_today)
    used_waivers: set[str] = set()
    waived_scenarios: set[str] = set()
    unwaived = []

    for transition in report.transitions:
        matching = next(
            (
                waiver
                for waiver in active_waivers
                if waiver.scenario_id == transition.scenario_id
                and waiver.from_effect is transition.baseline_effect
                and waiver.to_effect is transition.candidate_effect
                and waiver.action_fingerprint == transition.action_fingerprint
            ),
            None,
        )
        if matching is not None and transition.privilege_expansion:
            used_waivers.add(matching.id)
            waived_scenarios.add(transition.scenario_id)
        else:
            unwaived.append(transition)

    expansions = sum(item.privilege_expansion for item in unwaived)
    new_allows = sum(item.new_allow for item in unwaived)
    approval_bypasses = sum(item.approval_bypass for item in unwaived)
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

    unused = sorted(item.id for item in active_waivers if item.id not in used_waivers)
    if config.fail_on_unused_waivers and unused:
        violations.append(
            GateViolation(
                code="unused_waivers",
                message="active waivers do not match any privilege expansion",
                actual=len(unused),
                limit=0,
            )
        )

    return GateResult(
        passed=not violations,
        violations=violations,
        waived_scenarios=sorted(waived_scenarios),
        expired_waivers=expired,
        unused_waivers=unused,
    )


def strict_gate() -> GateConfig:
    """Return a zero-expansion, full-candidate-coverage release gate."""

    return GateConfig()


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
