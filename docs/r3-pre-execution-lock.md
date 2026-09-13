# R3 complete pre-execution evidence lock

## Status

**Lock contract:** `permitdiff.dev/r3-pre-execution-lock/v2`  
**Measurement contract:** `r3-exploratory-measurement-contract-v2`  
**Scope:** R3 exploratory pre-execution evidence only.

The lock is the final protocol gate before PermitDiff may be executed against the frozen
exploratory corpus. It does not execute PermitDiff and does not create benchmark results.

## Bound evidence

A successful lock cryptographically binds the exact bytes of:

- the machine-readable measurement contract;
- the benchmark manifest;
- deterministic public materialization;
- blinded review-packet set and every referenced packet artifact;
- multidimensional adjudications;
- decided scenario-channel provenance registry;
- manifest-integrity evidence; and
- scenario-channel-integrity evidence.

The lock records SHA-256 digests for every item above and the exact measurement-contract
version. Version strings alone are insufficient: the exact contract and scenario-registry
bytes are part of the frozen evidence state.

## Cross-artifact invariants

Before publishing the lock, the implementation requires:

- plan/protocol/measurement-contract version agreement across the evidence chain;
- a schema-valid measurement contract adopted before labels and product execution;
- review packets and scenario provenance bound to the exact materialization bytes;
- review-packet baseline/candidate provenance matches materialization and every referenced
  packet artifact validates against its declared SHA-256;
- adjudications bound to the exact blinded review-packet bytes;
- identical case membership across manifest, materialization, review packets,
  adjudications, and scenario-channel registry;
- every adjudication and scenario-channel case to be decided;
- manifest source provenance and adjudication payloads to match their upstream evidence;
- scenario provenance/admissibility and referenced scenario artifact SHA-256 values to
  validate under the frozen Task-4 contract; and
- no pre-existing PermitDiff result artifact anywhere in the common evidence root.

The implementation re-reads all top-level evidence inputs and all referenced review-packet
artifacts after integrity validation and refuses to publish if any bytes changed during lock
construction.

## Outputs

The output directory is created atomically and must not already exist. It contains:

- `manifest-integrity.json`;
- `scenario-channel-integrity.json`; and
- `pre-execution-lock.json`.

The scenario integrity artifact is versioned as
`permitdiff-r3-scenario-channel-integrity-v1`; manifest integrity remains versioned by the
existing benchmark-integrity validator.

## Invocation

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

`--measurement-contract` defaults to the canonical exploratory v2 contract, but the exact
file bytes supplied or resolved by the command are always validated and digest-bound.
`--scenario-channels` is mandatory because it is case-specific evidence.

## Evidence boundary

A successful lock establishes an immutable pre-execution evidence boundary. It does not
establish product accuracy, research novelty, external validation, production readiness,
or commercial validation. Those claims require later execution and independent evidence.
