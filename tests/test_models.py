from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from permitdiff.models import ActionContext, ActionRequest, Scenario


def test_fingerprint_ignores_request_identity_and_timestamp() -> None:
    first = ActionRequest(
        request_id="same",
        principal="p",
        agent="a",
        tool="t",
        arguments={"x": 1},
        requested_at=datetime.now(UTC),
    )
    second = first.model_copy(
        update={
            "request_id": "different",
            "requested_at": datetime.now(UTC) + timedelta(days=1),
        }
    )
    assert first.fingerprint() == second.fingerprint()


def test_fingerprint_changes_with_arguments() -> None:
    first = ActionRequest(principal="p", agent="a", tool="t", arguments={"x": 1})
    second = first.model_copy(update={"arguments": {"x": 2}})
    assert first.fingerprint() != second.fingerprint()


def test_identity_fields_are_trimmed() -> None:
    request = ActionRequest(principal=" p ", agent=" a ", tool=" t ", arguments={})
    assert (request.principal, request.agent, request.tool) == ("p", "a", "t")


def test_non_string_argument_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(
            principal="p",
            agent="a",
            tool="t",
            arguments={1: "bad"},  # type: ignore[dict-item]
        )


def test_non_finite_arguments_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ActionRequest(principal="p", agent="a", tool="t", arguments={"x": float("nan")})


def test_non_canonicalizable_integer_arguments_are_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot be canonicalized"):
        ActionRequest(
            principal="p",
            agent="a",
            tool="t",
            arguments={"x": 10**10_000},
        )


def test_non_canonicalizable_dynamic_context_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot be canonicalized"):
        ActionContext(tenant_metadata=10**10_000)


def test_non_json_dynamic_context_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-JSON value"):
        ActionContext(tenant_metadata=object())


def test_valid_dynamic_context_changes_action_fingerprint() -> None:
    first = ActionRequest(
        principal="p",
        agent="a",
        tool="t",
        context=ActionContext(tenant="alpha"),
    )
    second = first.model_copy(update={"context": ActionContext(tenant="beta")})
    assert first.fingerprint() != second.fingerprint()


def test_excessive_argument_depth_is_rejected() -> None:
    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(34):
        child: dict[str, object] = {}
        cursor["x"] = child
        cursor = child
    with pytest.raises(ValidationError):
        ActionRequest(principal="p", agent="a", tool="t", arguments=nested)


def test_scenario_tags_are_deduplicated_and_sorted() -> None:
    scenario = Scenario(
        id="case",
        action=ActionRequest(principal="p", agent="a", tool="t"),
        tags=[" z ", "a", "a", ""],
    )
    assert scenario.tags == ["a", "z"]


def test_scenario_id_has_stable_safe_syntax() -> None:
    with pytest.raises(ValidationError):
        Scenario(
            id="unsafe id",
            action=ActionRequest(principal="p", agent="a", tool="t"),
        )
