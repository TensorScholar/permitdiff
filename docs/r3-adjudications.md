# R3 output-blind adjudication and manifest freeze

## Status

This workflow records exploratory ground truth only after the blinded source-semantics
review packets exist. It remains independent of PermitDiff output. The resulting
adjudications and benchmark manifest are pre-execution evidence; they are not product
results and do not upgrade maturity.

The canonical adjudication contract for the amended exploratory study is
`permitdiff.dev/r3-adjudications/v2`, bound to
`r3-exploratory-measurement-contract-v2`.

## Prepare adjudication worksheet

```bash
python scripts/build_r3_exploratory_adjudications.py prepare \
  --review-packets validation/r3-benchmark/exploratory/review-packets-v2/review-packets.json \
  --output validation/r3-benchmark/exploratory/adjudications-v2.json
```

The generated worksheet is cryptographically bound to the exact review-packet-set bytes,
starts with every case in `pending` state, and fixes `product_output_consulted` to
`false`.

For each case, record these dimensions separately:

- `source_semantic_relation`: `WIDENING`, `RESTRICTIVE`, `EQUIVALENT`, `MIXED`, or
  `UNRESOLVED`;
- `tool_support`: `SUPPORTED`, `PARTIALLY_SUPPORTED`, or `UNSUPPORTED`;
- `organizational_intent`: `KNOWN_INTENDED`, `KNOWN_UNINTENDED`, `UNAVAILABLE`, or
  `NOT_APPLICABLE`;
- `source_semantics_resolution`: `RESOLVED`, `AMBIGUOUS`, or `UNAVAILABLE`;
- review status and reviewer identifiers;
- rationale and evidence references;
- atomic semantic categories and `change_family` where useful;
- ambiguity notes;
- `blinding_state`;
- `contamination_state`.

These dimensions are not aliases for one another. In particular, a source-level
`WIDENING` remains `WIDENING` when PermitDiff is `PARTIALLY_SUPPORTED` or `UNSUPPORTED`.
Likewise, `UNRESOLVED` describes source-semantic ground truth and is not a synonym for
tool unsupported behavior.

Any relation other than `UNRESOLVED` requires `RESOLVED` source semantics under the
frozen evidence set. `UNRESOLVED` requires `AMBIGUOUS` or `UNAVAILABLE` source semantics
plus explicit ambiguity notes.

`double_reviewed` and `adjudicated` require at least two distinct reviewer identifiers.
Do not represent AI assistance as an independent human reviewer.

## Manifest compatibility decision

The pre-amendment manifest contract
`permitdiff.dev/r3-benchmark-case-manifest/v1` embeds the superseded `label` and
`support_boundary` fields. It is preserved unchanged for historical compatibility and
must not be repurposed.

Canonical amended exploratory manifests use the separate schema:

- `docs/r3-benchmark-case-manifest-v2.schema.json`
- schema version: `permitdiff.dev/r3-benchmark-case-manifest/v2`

Manifest v2 records the four adjudication dimensions directly and contains no silent
mapping from `WIDENING` to `SECURITY_RELEVANT_REGRESSION`, nor from tool support to the
old support-boundary field.

## Build the exploratory public-historical manifest

The manifest must live beside `materialization.json` because artifact paths remain
relative to that evidence root:

```bash
python scripts/build_r3_exploratory_adjudications.py build-manifest \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --review-packets \
    validation/r3-benchmark/exploratory/review-packets-v2/review-packets.json \
  --adjudications \
    validation/r3-benchmark/exploratory/adjudications-v2.json \
  --output \
    validation/r3-benchmark/exploratory/public-historical-v1/manifest.json \
  --corpus-id r3-exploratory-public-historical-v1
```

The builder verifies digest linkages, rejects pending or product-contaminated
adjudications, preserves exact source commit/blob provenance, validates manifest v2, and
writes a non-null freeze timestamp.

No PermitDiff module is imported or executed by this workflow.

## Deliberately deferred to later tasks

This task does **not** define the normative review-trigger/scoring matrix for `MIXED`,
`UNRESOLVED`, supported-subset reporting, or abstention scoring. That contract must be
frozen separately before canonical labels are used for scoring.

Scenario-set provenance is also a separate artifact-chain decision. The manifest retains
the scenario-corpus slot, but this stage does not fabricate scenarios or infer provenance.

The pre-execution lock currently checks v2 contract/version consistency. A later lock
revision must additionally bind the exact machine-readable measurement-contract bytes.

## Evidence boundary

This stage freezes multidimensional, output-independent exploratory ground truth. It
still does not permit PermitDiff execution until the complete pre-execution lock has
bound all required evidence, including the measurement contract, and integrity
validation has succeeded.
