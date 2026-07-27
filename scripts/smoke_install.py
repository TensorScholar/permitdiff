#!/usr/bin/env python3
"""Smoke-test an installed distribution, including packaged starter data."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-m", "permitdiff.cli", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"command failed ({result.returncode}, expected {expected}): {args}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="permitdiff-smoke-") as directory:
        root = Path(directory) / "starter"
        run("init", str(root))
        output = run(
            "compare",
            str(root / "policies/baseline.yaml"),
            str(root / "policies/candidate.yaml"),
            str(root / "corpus.jsonl"),
            "--gate",
            str(root / "permitdiff-gate.yaml"),
            "--format",
            "json",
            expected=2,
        )
        payload = json.loads(output.stdout)
        assert payload["comparison"]["summary"]["approval_bypasses"] == 1
        assert payload["gate"]["passed"] is False
    print("installed distribution smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
