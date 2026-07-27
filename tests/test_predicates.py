from __future__ import annotations

import pytest

from permitdiff.policy import Predicate
from permitdiff.predicates import evaluate_predicate, resolve_path


def test_resolve_nested_object_and_list() -> None:
    assert resolve_path({"items": [{"price": 12}]}, "items.0.price") == 12


def test_resolve_missing_path_returns_sentinel_behavior() -> None:
    predicate = Predicate(path="items.9", operator="equals", value="x")
    assert not evaluate_predicate(predicate, {"items": []})


def test_exists() -> None:
    assert evaluate_predicate(Predicate(path="x", operator="exists", value=True), {"x": None})
    assert evaluate_predicate(Predicate(path="x", operator="exists", value=False), {})


def test_membership_operators() -> None:
    assert evaluate_predicate(
        Predicate(path="role", operator="in", value=["admin"]),
        {"role": "admin"},
    )
    assert evaluate_predicate(
        Predicate(path="role", operator="not_in", value=["admin"]),
        {"role": "user"},
    )


def test_contains_handles_wrong_types() -> None:
    predicate = Predicate(path="count", operator="contains", value=1)
    assert not evaluate_predicate(predicate, {"count": 2})


def test_glob_matching_is_case_sensitive() -> None:
    predicate = Predicate(path="name", operator="matches", value=["pay-*", "refund-*"])
    assert evaluate_predicate(predicate, {"name": "pay-create"})
    assert not evaluate_predicate(predicate, {"name": "Pay-create"})


def test_numeric_comparisons() -> None:
    assert evaluate_predicate(Predicate(path="x", operator="less_than", value=2), {"x": 1})
    assert evaluate_predicate(
        Predicate(path="x", operator="greater_than_or_equal", value=1), {"x": 1}
    )


def test_numeric_comparison_type_mismatch_is_false() -> None:
    predicate = Predicate(path="x", operator="greater_than", value="bad")
    assert not evaluate_predicate(predicate, {"x": 1})


def test_invalid_sequence_index_is_missing() -> None:
    predicate = Predicate(path="items.nope", operator="equals", value=1)
    assert not evaluate_predicate(predicate, {"items": [1]})


def test_unreachable_operator_returns_false() -> None:
    predicate = Predicate(path="x", operator="equals", value=1)
    object.__setattr__(predicate, "operator", "unsupported")
    assert not evaluate_predicate(predicate, {"x": 1})
