# R3 benchmark corpus scaffold

This directory implements the storage contract for the R3 benchmark protocol.

## Layout

- `exploratory/` is mutable engineering data used to debug the harness, refine schema choices, discover product defects, and clarify labels. Exploratory outcomes are not confirmatory product evidence.
- `confirmatory/` stays empty of executable cases until the protocol, schema, case list, source artifacts, adjudications, scoring code, tool versions, and exclusion policy are frozen.
- `docs/r3-benchmark-case-manifest.schema.json` is the canonical machine-readable case-manifest schema.

Each real case should live below `cases/<case-id>/` and should preserve the exact baseline, candidate, optional scenario corpus, and source/adjudication evidence needed to reproduce the label.

Do not copy the example manifest into confirmatory evidence. Its digests and reviewer identity are placeholders chosen only to demonstrate the schema shape.

## Integrity rules

1. Case IDs are stable.
2. Baseline/candidate artifacts are immutable once a confirmatory corpus is frozen.
3. Every artifact carries a SHA-256 digest.
4. Public historical sources should also retain immutable source commit/blob identifiers where available.
5. Ground truth is established without consulting PermitDiff output.
6. `UNKNOWN_OR_UNSUPPORTED` remains a first-class label and is never coerced into binary scoring.
7. Any change to a frozen confirmatory manifest requires a new benchmark version.

## Integrity validation

Install the development dependencies and validate a real manifest before executing any benchmark case:

```bash
uv pip install -e '.[dev]'
python scripts/validate_r3_benchmark_manifest.py \
  validation/r3-benchmark/exploratory/manifest.json \
  --output validation/r3-benchmark/exploratory/integrity.json
```

The validator:

- validates the manifest against the canonical JSON Schema using JSON Schema 2020-12 format checking;
- rejects duplicate case IDs;
- requires a non-null `frozen_at` timestamp for confirmatory manifests;
- resolves artifact paths relative to the manifest directory and rejects absolute paths, parent traversal, and symlink traversal;
- verifies baseline, candidate, and optional scenario-corpus SHA-256 digests from the local bytes;
- rejects partial immutable-source metadata that lacks a source URL;
- requires public historical/fixture baseline and candidate artifacts to carry an HTTP(S) source URL plus an immutable commit or blob identifier;
- emits deterministic machine-readable integrity evidence including the manifest digest and verified artifact sizes/digests;
- refuses to write its output over the manifest, schema, or any verified artifact.

`exploratory/manifest.example.json` is schema-only documentation. It intentionally refers to placeholder artifacts and digests and therefore is not expected to pass integrity validation.

The next implementation task is to assemble real exploratory cases under this contract, then build the benchmark execution/baseline harness. No confirmatory benchmark execution should begin until the exploratory path and freeze procedure have been exercised end to end.
