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

## Frozen review-trigger and scoring semantics

The normative review-trigger/scoring contract is now frozen before canonical labels and
before product execution:

- `docs/r3-review-trigger-scoring.md`
- `validation/r3-benchmark/exploratory/measurement-contract-v2.json`

`WIDENING` and `MIXED` are known review-required relations. `RESTRICTIVE` and
`EQUIVALENT` do not require review by the semantic-direction rule alone. `UNRESOLVED`
requires semantic escalation and is neither an ordinary positive nor negative.

Unsupported known review-required cases remain in the overall positive denominator.
Fail-closed blocking caused only by uncertainty/unsupported behavior is escalation, not
definite detection. A secondary `SUPPORTED` subset must be reported separately rather
than replacing the overall result.

## Frozen scenario provenance and explicit absent channel

Scenario-set provenance is now a separate, machine-readable pre-execution artifact:

- `docs/r3-scenario-channel-set.schema.json`;
- `docs/r3-scenario-provenance.md`;
- `scripts/build_r3_scenario_channels.py`.

Each selected case must explicitly record whether a primary-admissible observed-scenario
channel is `PRESENT` or `ABSENT`. `PREEXISTING_PROJECT` and `INDEPENDENT_BLIND` scenario
sets are primary-admissible. `DIAGNOSTIC_ANSWER_INFORMED` and `PRODUCT_GENERATED` are
diagnostic-only and cannot make the primary channel available.

An absent primary channel is a valid measured state and must use
`NO_PRIMARY_ADMISSIBLE_SCENARIO_SET`; no placeholder or answer-informed scenario corpus
may be fabricated to convert absence into presence. The existing manifest `scenario_corpus`
slot is not the canonical provenance carrier for this amended R3 workflow; scenario
provenance is frozen in the dedicated scenario-channel set and is digest-bound by the
complete v2 pre-execution lock.

## Complete pre-execution evidence lock

The pre-execution lock now requires the exact machine-readable measurement contract and
the decided scenario-channel set as first-class inputs. It validates their schemas and
cross-artifact linkage, verifies scenario artifact integrity, and binds their exact bytes
alongside the manifest, materialization, blinded review packets, adjudications, and
manifest-integrity evidence.

```bash
python scripts/lock_r3_exploratory_corpus_v2.py \
  --manifest \
    validation/r3-benchmark/exploratory/public-historical-v1/manifest.json \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --review-packets \
    validation/r3-benchmark/exploratory/review-packets-v2/review-packets.json \
  --adjudications \
    validation/r3-benchmark/exploratory/adjudications-v2.json \
  --measurement-contract \
    validation/r3-benchmark/exploratory/measurement-contract-v2.json \
  --scenario-channels \
    validation/r3-benchmark/exploratory/scenario-channels-v1.json \
  --output-dir \
    validation/r3-benchmark/exploratory/public-historical-v1/pre-execution-lock-v2
```

The lock publishes `manifest-integrity.json`, `scenario-channel-integrity.json`, and
`pre-execution-lock.json` atomically. The lock is schema-versioned as
`permitdiff.dev/r3-pre-execution-lock/v2` and records SHA-256 digests for every frozen
measurement/evidence input plus both integrity-evidence artifacts.

## Evidence boundary

This stage freezes multidimensional, output-independent exploratory ground truth, the
predeclared review/scoring interpretation, scenario provenance, and the exact evidence
chain required before product execution. It still does not itself run PermitDiff, create
benchmark outcomes, or upgrade maturity; product execution becomes protocol-permissible
only after a real corpus has been collected/adjudicated and this complete lock succeeds.
