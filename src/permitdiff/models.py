"""Immutable domain models for actions, scenarios, and decisions."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MAX_JSON_DEPTH = 32


class DecisionEffect(StrEnum):
    """Ordered authorization outcomes from least to most permissive."""

    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ALLOW = "allow"


class RiskLevel(StrEnum):
    """Scenario risk used for release reporting and gate severity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolAnnotations(BaseModel):
    """Security-relevant subset of MCP-style tool annotations.

    These values are hints, not evidence. ``ActionContext.security_metadata_trusted``
    records whether the corpus author independently established their trustworthiness.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    read_only: bool | None = None
    destructive: bool | None = None
    idempotent: bool | None = None
    open_world: bool | None = None


class ActionContext(BaseModel):
    """Runtime context considered by a permission policy."""

    model_config = ConfigDict(extra="allow", frozen=True)

    environment: str = Field(default="development", min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=256)
    trace_id: str | None = Field(default=None, max_length=256)
    source: str = Field(default="corpus", min_length=1, max_length=128)
    risk: RiskLevel | None = None
    security_metadata_trusted: bool = False

    @model_validator(mode="after")
    def extra_context_must_be_json_compatible(self) -> ActionContext:
        if self.model_extra:
            validate_json_value(self.model_extra, depth=0)
        return self


class ActionRequest(BaseModel):
    """A normalized pre-execution tool-call request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    principal: str = Field(min_length=1, max_length=256)
    agent: str = Field(min_length=1, max_length=256)
    tool: str = Field(min_length=1, max_length=512)
    arguments: dict[str, Any] = Field(default_factory=dict)
    annotations: ToolAnnotations = Field(default_factory=ToolAnnotations)
    context: ActionContext = Field(default_factory=ActionContext)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("request_id", "principal", "agent", "tool")
    @classmethod
    def normalized_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("arguments")
    @classmethod
    def arguments_must_be_json_compatible(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_json_value(value, depth=0)
        return value

    def fingerprint(self) -> str:
        """Return a stable digest for the permission-relevant action identity."""

        payload = self.model_dump(
            mode="json",
            exclude={"request_id", "requested_at"},
        )
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


class Scenario(BaseModel):
    """One reviewable action case in a permission regression corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    action: ActionRequest
    risk: RiskLevel = RiskLevel.MEDIUM
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=256)
    tags: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in values if item.strip()})
        if any(len(item) > 128 for item in normalized):
            raise ValueError("scenario tags must not exceed 128 characters")
        return normalized


class Decision(BaseModel):
    """A deterministic policy decision for one action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    effect: DecisionEffect
    reason: str
    rule_id: str | None = None
    policy_digest: str
    action_fingerprint: str


def validate_json_value(value: Any, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError(f"arguments exceed the maximum JSON depth of {_MAX_JSON_DEPTH}")
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        try:
            json.dumps(value, allow_nan=False)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("arguments contain an integer that cannot be canonicalized") from exc
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("arguments must not contain NaN or infinity")
        return
    if isinstance(value, list):
        for item in value:
            validate_json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("argument object keys must be strings")
            validate_json_value(item, depth + 1)
        return
    raise ValueError(f"arguments contain a non-JSON value of type {type(value).__name__}")
