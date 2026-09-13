# R3 blinded public review packets

## Status

This workflow prepares the output-independent evidence bundle used to adjudicate the
selected public historical slice. It is deliberately source-system-only: no PermitDiff
output, normalized policy, finding, gate result, or explanation is allowed into the
packet.

The packet contract implements `r3-exploratory-measurement-contract-v2`. It no longer
uses the superseded three-way label that conflated source-semantic direction, PermitDiff
support, organizational intent, and source-semantic uncertainty.

## 1. Prepare documentation context

After exact source artifacts have been materialized:

```bash
python scripts/build_r3_blinded_review_packets.py prepare \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --output validation/r3-benchmark/exploratory/review-context.json
```

The generated context is bound to the exact materialization-index bytes. It contains no
ground-truth decision fields.

Populate `common_documentation_refs` and/or each case's `documentation_refs` with the
public source-system documentation a reviewer may consult. Then change every case
`status` from `pending` to `ready`. Each documentation reference records a URL, title,
optional version/date, and optional notes.

This explicit context step prevents undocumented web browsing or case-specific
post-hoc evidence from silently entering the review condition.

## 2. Build self-contained packets

```bash
python scripts/build_r3_blinded_review_packets.py build \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --context validation/r3-benchmark/exploratory/review-context.json \
  --output-dir validation/r3-benchmark/exploratory/review-packets-v2
```

The builder verifies the materialization index and every copied artifact digest, requires
a ready context for every selected case, requires at least one public documentation
reference per case after common/case-specific references are merged, and publishes the
packet directory atomically.

Each case directory contains:

```text
baseline.json
candidate.json
source-diff.txt
review.md
```

`source-diff.txt` is a plain unified text diff with no PermitDiff-derived annotation.

`review.md` asks only the source-semantic questions governed by the measurement contract:

- exactly one `source_semantic_relation`:
  `WIDENING`, `RESTRICTIVE`, `EQUIVALENT`, `MIXED`, or `UNRESOLVED`;
- exactly one `source_semantics_resolution`:
  `RESOLVED`, `AMBIGUOUS`, or `UNAVAILABLE`.

Any relation other than `UNRESOLVED` requires `RESOLVED` source semantics under the
frozen evidence set.

The packet explicitly does **not** ask the reviewer to determine `tool_support` or
`organizational_intent`. Those are separate adjudication dimensions and must not change
the source-semantic relation. In particular, `UNRESOLVED` is not a synonym for
PermitDiff unsupported behavior.

The exploratory public-historical slice uses fixed-version semantic replay: reviewers
answer the source-semantic question under the frozen documented semantics and declared
review assumptions. The packet does not claim that current documentation proves the
historically deployed runtime behavior.

The top-level `review-packets.json` binds the packet schema version, measurement-contract
version, source materialization digest, review scope, frozen semantic definitions,
case metadata, and generated-file digests.

## Machine contracts

Context worksheets conform to:

- `docs/r3-review-context.schema.json`

Built packet sets conform to:

- `docs/r3-review-packet-set.schema.json`
- schema version `permitdiff.dev/r3-review-packet-set/v2`
- measurement contract `r3-exploratory-measurement-contract-v2`

## Blinding rule

A reviewer determines source semantics from the exact source artifacts, plain text diff,
and frozen public source-system documentation. Do not inspect PermitDiff output before
the provisional source-semantic adjudication is recorded.

The source-semantic question is:

> Under the frozen documented source semantics and declared review assumptions, what
> semantic relation holds between the exact baseline and candidate artifacts?

The packet itself does not determine whether PermitDiff supports those semantics, whether
the change was organizationally intended, or how the case should score against product
outputs. Those decisions belong to later, separately modeled adjudication/scoring
contracts.

## Evidence boundary

Packet construction is evidence preparation, not adjudication. A complete packet set
does not itself establish a semantic relation, product result, security defect, or
external validation.

The next step is to record multidimensional output-blind adjudications under the amended
measurement contract. Those adjudications must preserve source semantic relation, tool
support, organizational intent, and source-semantic resolution as separate dimensions
before PermitDiff execution.
