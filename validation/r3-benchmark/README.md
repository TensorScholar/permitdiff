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

The next implementation task after this scaffold is provenance/digest validation. No confirmatory benchmark execution should begin from this branch.
