#!/usr/bin/env python3
"""Frozen simple automated baseline for the PermitDiff R3 study."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "permitdiff.dev/r3-simple-baseline-result/v1"
ALGORITHM_VERSION = "r3-simple-native-change-checker-v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> tuple[bytes, object]:
    data = path.read_bytes()
    return data, json.loads(data.decode("utf-8"))


def _permission_array(permissions: dict[str, Any], name: str) -> list[str] | None:
    value = permissions.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return value


def evaluate(case_id: str, baseline_path: Path, candidate_path: Path) -> dict[str, object]:
    baseline_bytes = baseline_path.read_bytes()
    candidate_bytes = candidate_path.read_bytes()
    baseline_sha = _sha256(baseline_bytes)
    candidate_sha = _sha256(candidate_bytes)

    def result(
        disposition: str,
        *,
        reasons: list[str],
        added_allow: list[str] | None = None,
        removed_allow: list[str] | None = None,
        changed_fields: list[str] | None = None,
        error: str | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "algorithm_version": ALGORITHM_VERSION,
            "baseline_sha256": baseline_sha,
            "candidate_sha256": candidate_sha,
            "disposition": disposition,
            "reasons": reasons,
            "added_allow": sorted(added_allow or []),
            "removed_allow": sorted(removed_allow or []),
            "changed_fields": sorted(changed_fields or []),
            "error": error,
        }

    try:
        baseline = json.loads(baseline_bytes.decode("utf-8"))
        candidate = json.loads(candidate_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return result("ERROR", reasons=["invalid_json"], error=str(exc))

    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return result("UNKNOWN", reasons=["top_level_not_object"])

    baseline_permissions = baseline.get("permissions")
    candidate_permissions = candidate.get("permissions")
    if not isinstance(baseline_permissions, dict) or not isinstance(candidate_permissions, dict):
        return result("UNKNOWN", reasons=["permissions_not_object"])

    baseline_mode = baseline_permissions.get("defaultMode")
    candidate_mode = candidate_permissions.get("defaultMode")
    if baseline_mode != "dontAsk" or candidate_mode != "dontAsk":
        changed = []
        if baseline_mode != candidate_mode:
            changed.append("permissions.defaultMode")
        return result(
            "UNKNOWN",
            reasons=["default_mode_outside_frozen_dontAsk_scope"],
            changed_fields=changed,
        )

    baseline_allow = _permission_array(baseline_permissions, "allow")
    candidate_allow = _permission_array(candidate_permissions, "allow")
    baseline_ask = _permission_array(baseline_permissions, "ask")
    candidate_ask = _permission_array(candidate_permissions, "ask")
    baseline_deny = _permission_array(baseline_permissions, "deny")
    candidate_deny = _permission_array(candidate_permissions, "deny")
    if None in (
        baseline_allow,
        candidate_allow,
        baseline_ask,
        candidate_ask,
        baseline_deny,
        candidate_deny,
    ):
        return result("UNKNOWN", reasons=["permission_array_has_unsupported_shape"])

    assert baseline_allow is not None
    assert candidate_allow is not None
    assert baseline_ask is not None
    assert candidate_ask is not None
    assert baseline_deny is not None
    assert candidate_deny is not None

    added_allow = sorted(set(candidate_allow) - set(baseline_allow))
    removed_allow = sorted(set(baseline_allow) - set(candidate_allow))
    changed_fields: list[str] = []
    reasons: list[str] = []

    if added_allow or removed_allow:
        changed_fields.append("permissions.allow")
    if baseline_ask != candidate_ask:
        changed_fields.append("permissions.ask")
    if baseline_deny != candidate_deny:
        changed_fields.append("permissions.deny")

    if added_allow:
        reasons.append("candidate_adds_raw_allow_entry")
    if baseline_ask != candidate_ask:
        reasons.append("permissions_ask_changed")
    if baseline_deny != candidate_deny:
        reasons.append("permissions_deny_changed")

    if reasons:
        return result(
            "REVIEW_REQUIRED",
            reasons=reasons,
            added_allow=added_allow,
            removed_allow=removed_allow,
            changed_fields=changed_fields,
        )

    return result(
        "NO_REVIEW_REQUIRED",
        reasons=["no_new_raw_allow_and_ask_deny_unchanged"],
        added_allow=added_allow,
        removed_allow=removed_allow,
        changed_fields=changed_fields,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = evaluate(args.case_id, args.baseline, args.candidate)
    except OSError as exc:
        parser.error(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
