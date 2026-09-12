# R3 output-blind adjudication and manifest freeze

## Status

This workflow records exploratory ground truth only after the blinded review packets exist.
It must remain independent of PermitDiff output. The resulting adjudications and manifest
are pre-execution evidence; they are not product results and do not upgrade maturity.

## Prepare adjudication worksheet

```bash
python scripts/build_r3_exploratory_adjudications.py prepare \
  --review-packets validation/r3-benchmark/exploratory/review-packets-v1/review-packets.json \
  --output validation/r3-benchmark/exploratory/adjudications-v1.json
```

The generated worksheet is cryptographically bound to the exact review packet set and
starts with every case in `pending` state. `product_output_consulted` is fixed to `false`.

For each case, record:

- one protocol label;
- support-boundary expectation;
- review status;
- reviewer identifiers;
- explicit rationale;
- atomic categories where applicable;
- evidence references;
- ambiguity notes where applicable;
- one `change_family` value for manifest grouping.

A positive `SECURITY_RELEVANT_REGRESSION` requires at least one atomic category.
`double_reviewed` and `adjudicated` require at least two distinct reviewer identifiers.
Do not use those statuses to represent AI assistance as a second independent human review.

## Build the exploratory public-historical manifest

The manifest must live beside `materialization.json` because artifact paths are kept
relative to that evidence root:

```bash
python scripts/build_r3_exploratory_adjudications.py build-manifest \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --review-packets \
    validation/r3-benchmark/exploratory/review-packets-v1/review-packets.json \
  --adjudications \
    validation/r3-benchmark/exploratory/adjudications-v1.json \
  --output \
    validation/r3-benchmark/exploratory/public-historical-v1/manifest.json \
  --corpus-id r3-exploratory-public-historical-v1
```

The builder verifies all digest linkages, refuses pending or contaminated adjudications,
preserves exact source commit/blob provenance, validates the canonical R3 manifest schema,
and writes a non-null freeze timestamp.

No PermitDiff module is imported or executed by this workflow.

## Evidence boundary

This stage freezes output-independent exploratory ground truth. It still does not permit
PermitDiff execution until the complete pre-execution lock has also verified manifest
integrity and the evidence chain.
