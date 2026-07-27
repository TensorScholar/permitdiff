#!/usr/bin/env python3
"""Generate public JSON Schemas and fail on schema drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from permitdiff.analysis import ComparisonReport
from permitdiff.gate import GateConfig, GateResult
from permitdiff.policy import PolicyDocument
from permitdiff.reporting import ReportEnvelope

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS: dict[Path, dict[str, Any]] = {
    ROOT / "docs/policy.schema.json": PolicyDocument.model_json_schema(),
    ROOT / "docs/gate.schema.json": GateConfig.model_json_schema(),
    ROOT / "docs/comparison-report.schema.json": ComparisonReport.model_json_schema(),
    ROOT / "docs/gate-result.schema.json": GateResult.model_json_schema(),
    ROOT / "docs/report-bundle.schema.json": ReportEnvelope.model_json_schema(),
}


def encoded(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed schemas differ from generated schemas",
    )
    args = parser.parse_args()
    stale: list[Path] = []
    for path, schema in OUTPUTS.items():
        content = encoded(schema)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(path.relative_to(ROOT))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if stale:
        print("schema drift detected:")
        for path in stale:
            print(f"  {path}")
        print("run: python scripts/generate_schemas.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
