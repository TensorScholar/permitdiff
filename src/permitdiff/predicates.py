"""Safe predicate evaluation over JSON-like action arguments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from typing import Any

from permitdiff.policy import Predicate

_MISSING = object()


def resolve_path(document: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted path with non-negative list indexes; never execute expressions."""

    current: Any = document
    for segment in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(segment, _MISSING)
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes, bytearray)):
            if not segment.isdecimal():
                return _MISSING
            try:
                current = current[int(segment)]
            except IndexError:
                return _MISSING
        else:
            return _MISSING
        if current is _MISSING:
            return _MISSING
    return current


def evaluate_predicate(predicate: Predicate, arguments: Mapping[str, Any]) -> bool:
    """Evaluate one bounded, non-executable predicate."""

    actual = resolve_path(arguments, predicate.path)
    op = predicate.operator
    expected = predicate.value

    if op == "exists":
        return (actual is not _MISSING) is expected
    if actual is _MISSING:
        return False
    if op == "equals":
        return bool(actual == expected)
    if op == "not_equals":
        return bool(actual != expected)
    if op in {"in", "not_in"}:
        try:
            result = actual in expected
        except TypeError:
            return False
        return result if op == "in" else not result
    if op == "contains":
        try:
            return bool(expected in actual)
        except TypeError:
            return False
    if op == "matches":
        if not isinstance(actual, str):
            return False
        patterns = [expected] if isinstance(expected, str) else expected
        return isinstance(patterns, list) and any(
            isinstance(pattern, str) and fnmatchcase(actual, pattern) for pattern in patterns
        )
    if op == "less_than":
        return _ordered_compare(actual, expected, "lt")
    if op == "less_than_or_equal":
        return _ordered_compare(actual, expected, "le")
    if op == "greater_than":
        return _ordered_compare(actual, expected, "gt")
    if op == "greater_than_or_equal":
        return _ordered_compare(actual, expected, "ge")
    return False


def _ordered_compare(actual: Any, expected: Any, operator: str) -> bool:
    try:
        if operator == "lt":
            return bool(actual < expected)
        if operator == "le":
            return bool(actual <= expected)
        if operator == "gt":
            return bool(actual > expected)
        return bool(actual >= expected)
    except TypeError:
        return False
