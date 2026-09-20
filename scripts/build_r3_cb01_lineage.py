#!/usr/bin/env python3
"""Thin CB-01 construction-lineage CLI (Packet B Phase B1).

This module is a thin orchestration wrapper only. The sole semantic
authority remains ``scripts.r3_cb01_corpus_construction``. This file must
not recompute selection keys, contamination status, digests, validation
rules, or schema logic. It reads exact file bytes, delegates to
``cb01.derive_lineage_v1``, and writes the result atomically.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import scripts.r3_cb01_corpus_construction as cb01


def _read_exact_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    """Read exact file bytes and parse them as a JSON object."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise cb01.CB01ConstructionError(f"failed to read {label} {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise cb01.CB01ConstructionError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise cb01.CB01ConstructionError(f"{label} must contain a JSON object: {path}")
    return payload, raw


def _write_atomic(output: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON atomically so failures leave no partial output file."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{output.name}.staging-",
        dir=str(output.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, output)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def build_lineage(
    *,
    raw_path: Path,
    decisions_path: Path,
    screened_path: Path,
    selection_path: Path,
    contract_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Build lineage from exact on-disk bytes via the CB-01 pure module."""
    raw, raw_bytes = _read_exact_json(raw_path, label="raw ledger")
    decisions, decisions_bytes = _read_exact_json(decisions_path, label="screening decisions")
    screened, screened_bytes = _read_exact_json(screened_path, label="screened ledger")
    selection, selection_bytes = _read_exact_json(selection_path, label="public selection")
    contract, contract_bytes = _read_exact_json(contract_path, label="CB-01 contract")
    lineage = cb01.derive_lineage_v1(
        raw,
        raw_bytes,
        decisions,
        decisions_bytes,
        screened,
        screened_bytes,
        selection,
        selection_bytes,
        contract,
        contract_bytes,
    )
    _write_atomic(output_path, lineage)
    return lineage


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint: build lineage or fail closed with no partial output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-ledger", type=Path, required=True)
    parser.add_argument("--screening-decisions", type=Path, required=True)
    parser.add_argument("--screened-ledger", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        build_lineage(
            raw_path=args.raw_ledger,
            decisions_path=args.screening_decisions,
            screened_path=args.screened_ledger,
            selection_path=args.selection,
            contract_path=args.contract,
            output_path=args.output,
        )
    except cb01.CB01ConstructionError as exc:
        print(f"R3 CB-01 lineage failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"R3 CB-01 lineage failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
