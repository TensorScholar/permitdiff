# R3 blinded public review packets

## Status

This workflow prepares the output-independent evidence bundle used to adjudicate the
selected public historical slice. It is deliberately source-system-only: no PermitDiff
output, normalized policy, finding, gate result, or explanation is allowed into the
packet.

## 1. Prepare documentation context

After exact source artifacts have been materialized:

```bash
python scripts/build_r3_blinded_review_packets.py prepare \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --output validation/r3-benchmark/exploratory/review-context.json
```

The generated context is bound to the exact materialization-index bytes. It contains no
ground-truth label fields.

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
  --output-dir validation/r3-benchmark/exploratory/review-packets-v1
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
`review.md` states the fixed review question, the three protocol labels, source
provenance, packet files, and the allowed source-system documentation.

The top-level `review-packets.json` binds packet metadata and generated-file digests.

## Machine contracts

Context worksheets conform to:

- `docs/r3-review-context.schema.json`

Built packet sets conform to:

- `docs/r3-review-packet-set.schema.json`

## Blinding rule

A reviewer must decide ground truth from the exact source artifacts, plain text diff,
and documented public source-system semantics. Do not inspect PermitDiff output before
the provisional adjudication is recorded.

The packet labels are:

- `SECURITY_RELEVANT_REGRESSION`
- `BENIGN_OR_RESTRICTIVE_CHANGE`
- `UNKNOWN_OR_UNSUPPORTED`

When public documentation is insufficient or runtime/precedence semantics remain
genuinely ambiguous, the protocol requires `UNKNOWN_OR_UNSUPPORTED` instead of a forced
binary judgment.

## Evidence boundary

Packet construction is evidence preparation, not adjudication. A complete packet set
does not itself establish a security label or external validation.

The next step is to record output-blind provisional adjudications, including rationale,
evidence references, support-boundary status, review status, and atomic categories where
required. Those records must be locked into the benchmark manifest before PermitDiff
execution.
