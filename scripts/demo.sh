#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHONPATH=src python -m permitdiff.cli policy validate examples/baseline.yaml
PYTHONPATH=src python -m permitdiff.cli corpus validate examples/corpus.jsonl

set +e
PYTHONPATH=src python -m permitdiff.cli compare \
  examples/baseline.yaml \
  examples/candidate.yaml \
  examples/corpus.jsonl \
  --gate examples/gate.yaml
status=$?
set -e

if [[ "$status" -ne 2 ]]; then
  echo "expected the example gate to fail with exit code 2; got $status" >&2
  exit 1
fi

echo "demo passed: the intentional permission expansion was blocked"
