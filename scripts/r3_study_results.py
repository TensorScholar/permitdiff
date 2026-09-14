#!/usr/bin/env python3
"""Validate and derive R3 study results from lock-bound raw records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REQUIRED_TERMINAL_CONDITIONS = (
    "PERMITDIFF_MACHINE",
    "SIMPLE_AUTOMATED_BASELINE",
    "PERMITDIFF_ASSISTED",
    "STRUCTURED_MANUAL",
    "SOURCE_TEXT_DIFF",
)
INTERPRETATION_VERSION = "r3-primary-interpretation-v1"


class StudyResultError(ValueError):
    """Raised when R3 result evidence is incomplete, inconsistent, or non-canonical."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def canonical_rate(numerator: int, denominator: int) -> dict[str, int | float | None]:
    if isinstance(numerator, bool) or isinstance(denominator, bool):
        raise StudyResultError("rate counts must be integers")
    if not isinstance(numerator, int) or not isinstance(denominator, int):
        raise StudyResultError("rate counts must be integers")
    if numerator < 0 or denominator < 0:
        raise StudyResultError("rate counts must be non-negative")
    if numerator > denominator:
        raise StudyResultError("rate numerator cannot exceed denominator")
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": None if denominator == 0 else numerator / denominator,
    }


def validate_rate(value: Mapping[str, Any]) -> None:
    expected = canonical_rate(value.get("numerator"), value.get("denominator"))
    observed = value.get("rate")
    expected_rate = expected["rate"]
    if expected_rate is None:
        if observed is not None:
            raise StudyResultError("zero-denominator rate must be null")
        return
    if not isinstance(observed, (int, float)) or isinstance(observed, bool):
        raise StudyResultError("non-zero-denominator rate must be numeric")
    if not math.isclose(float(observed), float(expected_rate), rel_tol=0.0, abs_tol=1e-12):
        raise StudyResultError("caller-supplied rate does not match canonical arithmetic")


def linear_quantile(values: Sequence[float], p: float) -> float:
    if not values:
        raise StudyResultError("quantile requires at least one value")
    ordered = sorted(float(value) for value in values)
    if any(value < 0 or not math.isfinite(value) for value in ordered):
        raise StudyResultError("timing values must be finite and non-negative")
    if not 0.0 <= p <= 1.0:
        raise StudyResultError("quantile probability must be within [0, 1]")
    if len(ordered) == 1:
        return ordered[0]
    h = (len(ordered) - 1) * p
    lower = math.floor(h)
    upper = math.ceil(h)
    if lower == upper:
        return ordered[lower]
    fraction = h - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize_timing(values: Sequence[float]) -> dict[str, int | float | None]:
    if not values:
        return {
            "timing_valid_case_count": 0,
            "q1_active_seconds": None,
            "median_active_seconds": None,
            "q3_active_seconds": None,
            "iqr_active_seconds": None,
            "total_active_seconds": None,
        }
    q1 = linear_quantile(values, 0.25)
    median = linear_quantile(values, 0.5)
    q3 = linear_quantile(values, 0.75)
    return {
        "timing_valid_case_count": len(values),
        "q1_active_seconds": q1,
        "median_active_seconds": median,
        "q3_active_seconds": q3,
        "iqr_active_seconds": q3 - q1,
        "total_active_seconds": float(sum(values)),
    }


def derive_top_level_outcome(
    *,
    invalidated: bool,
    automatic_pass_error_count: int,
    permitdiff_escalation_burden: float | None,
    assisted_missed: int,
    manual_missed: int,
    assisted_false_alerts: int,
    manual_false_alerts: int,
    permitdiff_recall: float | None,
    simple_baseline_recall: float | None,
    assisted_escalations: int,
    manual_escalations: int,
    timing_complete: bool,
    assisted_median_seconds: float | None,
    manual_median_seconds: float | None,
    assisted_total_seconds: float | None,
    manual_total_seconds: float | None,
) -> tuple[str, list[str]]:
    """Derive the frozen R3 primary interpretation with no operator-selected branch."""

    if invalidated:
        return "INVALIDATED", ["STUDY_VERSION_INVALIDATED"]
    if automatic_pass_error_count > 0:
        return "SAFETY_FAILURE", ["AUTOMATIC_PASS_ERROR_ON_NATURAL_POSITIVE"]
    if permitdiff_escalation_burden is None:
        return "MIXED_INCONCLUSIVE", ["PRIMARY_ESCALATION_DENOMINATOR_UNAVAILABLE"]
    if permitdiff_escalation_burden > (1.0 / 3.0):
        return "MIXED_INCONCLUSIVE", ["PRIMARY_ESCALATION_BURDEN_EXCEEDS_ONE_THIRD"]

    supported_data_available = permitdiff_recall is not None and simple_baseline_recall is not None
    if (
        supported_data_available
        and assisted_missed < manual_missed
        and assisted_false_alerts <= manual_false_alerts
        and float(permitdiff_recall) > float(simple_baseline_recall)
    ):
        return "SUPPORTED", ["DETECTION_ADVANTAGE_WITHOUT_FALSE_ALERT_INCREASE"]

    effort_threshold_met = False
    if timing_complete:
        timing_values = (
            assisted_median_seconds,
            manual_median_seconds,
            assisted_total_seconds,
            manual_total_seconds,
        )
        if all(value is not None for value in timing_values):
            assert assisted_median_seconds is not None
            assert manual_median_seconds is not None
            assert assisted_total_seconds is not None
            assert manual_total_seconds is not None
            effort_threshold_met = (
                assisted_median_seconds <= 0.8 * manual_median_seconds
                and assisted_total_seconds <= 0.8 * manual_total_seconds
            )

    if (
        assisted_missed == manual_missed
        and assisted_false_alerts <= manual_false_alerts
        and assisted_escalations <= manual_escalations
        and effort_threshold_met
    ):
        return "EFFORT_ADVANTAGE_ONLY", ["FROZEN_TWENTY_PERCENT_EFFORT_ADVANTAGE"]

    if (
        supported_data_available
        and timing_complete
        and assisted_missed >= manual_missed
        and not effort_threshold_met
    ):
        return "NO_MEANINGFUL_ADVANTAGE", ["NO_DETECTION_OR_FROZEN_EFFORT_ADVANTAGE"]

    reasons: list[str] = []
    if not supported_data_available:
        reasons.append("REQUIRED_COMPARATIVE_DENOMINATOR_UNAVAILABLE")
    if not timing_complete:
        reasons.append("EFFORT_TIMING_INCOMPLETE")
    if not reasons:
        reasons.append("CONFLICTING_PRIMARY_TRADEOFFS")
    return "MIXED_INCONCLUSIVE", reasons


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise StudyResultError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StudyResultError(f"{label} must be a JSON object")
    return value, raw


def _validate_schema(value: dict[str, Any], schema_path: Path, label: str) -> None:
    schema, _ = _load_json(schema_path, f"{label} schema")
    Draft202012Validator.check_schema(schema)
    error = next(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value), None
    )
    if error is not None:
        raise StudyResultError(f"{label} schema validation failed: {error.message}")


def validate_terminal_completeness(result_set: Mapping[str, Any], case_ids: Sequence[str]) -> None:
    expected = {
        (case_id, condition) for case_id in case_ids for condition in REQUIRED_TERMINAL_CONDITIONS
    }
    rows = result_set.get("terminal_states")
    if not isinstance(rows, list):
        raise StudyResultError("terminal_states must be a list")
    seen: dict[tuple[str, str], str] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise StudyResultError("terminal state must be an object")
        case_id = raw.get("case_id")
        condition = raw.get("condition")
        state = raw.get("state")
        if (
            not isinstance(case_id, str)
            or not isinstance(condition, str)
            or not isinstance(state, str)
        ):
            raise StudyResultError("terminal state is malformed")
        key = (case_id, condition)
        if key in seen:
            raise StudyResultError(f"duplicate terminal state: {key}")
        seen[key] = state
    if set(seen) != expected:
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected)
        raise StudyResultError(
            f"terminal-state population mismatch; missing={missing}, extra={extra}"
        )


def _records_by_case(records: Any, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(records, list):
        raise StudyResultError(f"{label} must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for raw in records:
        if not isinstance(raw, Mapping):
            raise StudyResultError(f"{label} entry must be an object")
        case_id = raw.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise StudyResultError(f"{label} entry has invalid case_id")
        if case_id in result:
            raise StudyResultError(f"duplicate {label} case_id: {case_id}")
        result[case_id] = raw
    return result


def validate_result_set(
    result_set: dict[str, Any],
    *,
    pre_execution_lock: dict[str, Any],
    result_set_schema: Path,
    records_schema: Path,
) -> None:
    _validate_schema(result_set, result_set_schema, "result set")
    case_ids = pre_execution_lock.get("case_ids")
    if not isinstance(case_ids, list) or not all(isinstance(case_id, str) for case_id in case_ids):
        raise StudyResultError("pre-execution lock has invalid case_ids")
    lock_sha = canonical_json_sha256(pre_execution_lock)
    if result_set.get("pre_execution_lock_sha256") != lock_sha:
        raise StudyResultError("result set does not bind the supplied pre-execution lock")
    validate_terminal_completeness(result_set, case_ids)

    records_schema_value, _ = _load_json(records_schema, "records schema")
    Draft202012Validator.check_schema(records_schema_value)
    validator = Draft202012Validator(records_schema_value, format_checker=FormatChecker())
    for collection in (
        "permitdiff_results",
        "simple_baseline_results",
        "human_reviews",
        "invalidations",
        "disagreements",
    ):
        records = result_set.get(collection)
        if not isinstance(records, list):
            raise StudyResultError(f"{collection} must be a list")
        for record in records:
            error = next(validator.iter_errors(record), None)
            if error is not None:
                raise StudyResultError(f"{collection} record schema failure: {error.message}")
            if record.get("pre_execution_lock_sha256") != lock_sha:
                raise StudyResultError(f"{collection} contains a cross-study record")

    permitdiff = _records_by_case(result_set.get("permitdiff_results"), "permitdiff_results")
    baseline = _records_by_case(
        result_set.get("simple_baseline_results"), "simple_baseline_results"
    )
    for case_id in case_ids:
        states = {
            row["condition"]: row["state"]
            for row in result_set["terminal_states"]
            if row["case_id"] == case_id
        }
        if states["PERMITDIFF_MACHINE"] == "RECORDED" and case_id not in permitdiff:
            raise StudyResultError(
                f"missing PermitDiff record for terminal RECORDED case {case_id}"
            )
        if states["SIMPLE_AUTOMATED_BASELINE"] == "RECORDED" and case_id not in baseline:
            raise StudyResultError(f"missing baseline record for terminal RECORDED case {case_id}")

    assisted_hashes = {
        canonical_json_sha256(record): record for record in result_set.get("permitdiff_results", [])
    }
    for record in result_set.get("human_reviews", []):
        if record.get("condition") != "PERMITDIFF_ASSISTED":
            continue
        target = record.get("permitdiff_result_record_sha256")
        if target not in assisted_hashes:
            raise StudyResultError("assisted review does not bind a canonical PermitDiff record")
        if assisted_hashes[target].get("case_id") != record.get("case_id"):
            raise StudyResultError("assisted review binds a PermitDiff record from another case")

    comparative = result_set.get("comparative_analysis")
    if not isinstance(comparative, Mapping):
        raise StudyResultError("comparative_analysis must be an object")
    for section in ("permitdiff", "simple_automated_baseline"):
        raw = comparative.get(section)
        if not isinstance(raw, Mapping):
            raise StudyResultError(f"comparative_analysis.{section} must be an object")
        for rate in raw.values():
            if isinstance(rate, Mapping) and {"numerator", "denominator", "rate"} <= set(rate):
                validate_rate(rate)
    for section in ("permitdiff_assisted", "structured_manual"):
        raw = comparative.get(section)
        if not isinstance(raw, Mapping):
            raise StudyResultError(f"comparative_analysis.{section} must be an object")
        agreement = raw.get("agreement_with_reference")
        if isinstance(agreement, Mapping):
            validate_rate(agreement)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--result-set", type=Path, required=True)
    parser.add_argument("--pre-execution-lock", type=Path, required=True)
    parser.add_argument(
        "--result-set-schema",
        type=Path,
        default=root / "docs/r3-study-result-set.schema.json",
    )
    parser.add_argument(
        "--records-schema",
        type=Path,
        default=root / "docs/r3-freeze-completion-records-v2.schema.json",
    )
    args = parser.parse_args(argv)
    try:
        result_set, _ = _load_json(args.result_set, "result set")
        lock, _ = _load_json(args.pre_execution_lock, "pre-execution lock")
        validate_result_set(
            result_set,
            pre_execution_lock=lock,
            result_set_schema=args.result_set_schema,
            records_schema=args.records_schema,
        )
    except (StudyResultError, OSError, ValueError, KeyError) as exc:
        print(f"R3 study-result validation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
