#!/usr/bin/env python3
"""Reproducible local benchmark for the deterministic comparison path."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from permitdiff import __version__
from permitdiff.analysis import compare_policies
from permitdiff.models import ActionContext, ActionRequest, RiskLevel, Scenario, ToolAnnotations
from permitdiff.policy import PolicyDocument

ROOT = Path(__file__).resolve().parents[1]


def scenarios(count: int) -> list[Scenario]:
    result: list[Scenario] = []
    for index in range(count):
        amount = (index % 20000) + 1
        tool = "billing.refund" if index % 3 else "crm.lookup_customer"
        destructive = tool == "billing.refund"
        result.append(
            Scenario(
                id=f"benchmark-{index:06d}",
                risk=RiskLevel.HIGH if destructive else RiskLevel.LOW,
                action=ActionRequest(
                    request_id=f"benchmark-{index:06d}",
                    principal="role:support",
                    agent="agent:benchmark",
                    tool=tool,
                    arguments={"amount": amount, "customer_id": f"C-{index}"},
                    annotations=ToolAnnotations(
                        read_only=not destructive,
                        destructive=destructive,
                        idempotent=not destructive,
                        open_world=False,
                    ),
                    context=ActionContext(
                        environment="benchmark",
                        source="generated",
                        security_metadata_trusted=True,
                    ),
                ),
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", type=int, default=20000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.scenarios < 1 or args.runs < 1:
        parser.error("--scenarios and --runs must be positive")

    baseline = PolicyDocument.from_yaml(ROOT / "examples/baseline.yaml")
    candidate = PolicyDocument.from_yaml(ROOT / "examples/candidate.yaml")
    corpus = scenarios(args.scenarios)

    durations: list[float] = []
    for _ in range(args.runs):
        start = time.perf_counter()
        report = compare_policies(baseline, candidate, corpus)
        durations.append(time.perf_counter() - start)
    median = statistics.median(durations)
    payload = {
        "schema_version": "permitdiff.benchmark/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "permitdiff_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "scenarios": args.scenarios,
        "runs": args.runs,
        "durations_seconds": durations,
        "median_seconds": median,
        "median_scenarios_per_second": args.scenarios / median,
        "candidate_digest": report.candidate_digest,
        "corpus_digest": report.corpus_digest,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
