"""Permission policy schema, validation, and canonical hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from permitdiff.errors import PolicyLoadError
from permitdiff.models import DecisionEffect, RiskLevel, validate_json_value

_MAX_POLICY_BYTES = 1_000_000

Operator = Literal[
    "equals",
    "not_equals",
    "in",
    "not_in",
    "contains",
    "matches",
    "exists",
    "less_than",
    "less_than_or_equal",
    "greater_than",
    "greater_than_or_equal",
]


class Predicate(BaseModel):
    """Predicate against a dotted JSON path in action arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=512)
    operator: Operator
    value: Any = None

    @model_validator(mode="after")
    def validate_value(self) -> "Predicate":
        validate_json_value(self.value)
        if self.operator == "exists":
            if not isinstance(self.value, bool):
                raise ValueError("operator 'exists' requires a boolean value")
            return self
        if self.value is None:
            raise ValueError(f"operator {self.operator!r} requires a value")
        if self.operator == "matches":
            patterns = [self.value] if isinstance(self.value, str) else self.value
            if not isinstance(patterns, list) or not patterns:
                raise ValueError("operator 'matches' requires a glob string or non-empty list")
            if any(not isinstance(item, str) or len(item) > 512 for item in patterns):
                raise ValueError("glob patterns must be strings no longer than 512 characters")
        return self


class RuleMatch(BaseModel):
    """All configured dimensions must match; values within a dimension are ORed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: list[str] = Field(default_factory=lambda: ["*"])
    principals: list[str] = Field(default_factory=lambda: ["*"])
    agents: list[str] = Field(default_factory=lambda: ["*"])
    environments: list[str] = Field(default_factory=lambda: ["*"])
    sources: list[str] = Field(default_factory=lambda: ["*"])
    risks: list[RiskLevel] = Field(default_factory=list)
    security_metadata_trusted: bool | None = None
    read_only: bool | None = None
    destructive: bool | None = None
    idempotent: bool | None = None
    open_world: bool | None = None
    arguments: list[Predicate] = Field(default_factory=list)

    @field_validator("tools", "principals", "agents", "environments", "sources")
    @classmethod
    def validate_glob_list(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("glob match lists must not be empty")
        if any(not item or len(item) > 512 for item in values):
            raise ValueError("glob patterns must be non-empty and at most 512 characters")
        return values


class PolicyRule(BaseModel):
    """Ordered first-match policy rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    description: str = Field(min_length=1, max_length=1000)
    effect: DecisionEffect
    match: RuleMatch = Field(default_factory=RuleMatch)

    @model_validator(mode="after")
    def require_explicit_annotation_trust_for_allow(self) -> "PolicyRule":
        uses_annotation_metadata = bool(self.match.risks) or any(
            value is not None
            for value in (
                self.match.read_only,
                self.match.destructive,
                self.match.idempotent,
                self.match.open_world,
            )
        )
        if (
            self.effect is DecisionEffect.ALLOW
            and uses_annotation_metadata
            and self.match.security_metadata_trusted is not True
        ):
            raise ValueError(
                "allow rules using annotation-derived metadata must require "
                "security_metadata_trusted: true"
            )
        return self


class PolicyMetadata(BaseModel):
    """Human-readable policy metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)


class PolicyDocument(BaseModel):
    """Complete deterministic permission policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_version: Literal["permitdiff.dev/v1alpha1"] = "permitdiff.dev/v1alpha1"
    kind: Literal["Policy"] = "Policy"
    metadata: PolicyMetadata
    default_effect: DecisionEffect = DecisionEffect.DENY
    rules: list[PolicyRule]

    @model_validator(mode="after")
    def unique_rule_ids(self) -> "PolicyDocument":
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PolicyDocument":
        policy_path = Path(path)
        try:
            if policy_path.stat().st_size > _MAX_POLICY_BYTES:
                raise ValueError(f"policy exceeds {_MAX_POLICY_BYTES} bytes")
            raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("policy root must be a mapping")
            return cls.model_validate(raw)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
            raise PolicyLoadError(f"failed to load policy {policy_path}: {exc}") from exc

    def digest(self) -> str:
        """Return a canonical SHA-256 digest of the validated policy document."""

        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
