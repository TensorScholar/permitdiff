# R3 exploratory pre-execution lock

## Purpose

The pre-execution lock is the final guard before PermitDiff may be run against the frozen
exploratory public-historical corpus. It verifies the evidence chain without importing or
executing PermitDiff analysis code.

The lock checks:

- canonical benchmark-manifest schema and artifact digests;
- materialization schema and exact public-source provenance;
- review-packet schema and materialization digest binding;
- output-blind adjudication schema and review-packet digest binding;
- exact case membership across all four artifacts;
- exact manifest baseline/candidate provenance against materialization;
- exact manifest adjudications against the frozen decisions;
- absence of known PermitDiff result artifacts before the lock is produced.

## Command

```bash
python scripts/lock_r3_exploratory_corpus.py \
  --manifest \
    validation/r3-benchmark/exploratory/public-historical-v1/manifest.json \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --review-packets \
    validation/r3-benchmark/exploratory/review-packets-v1/review-packets.json \
  --adjudications \
    validation/r3-benchmark/exploratory/adjudications-v1.json \
  --output-dir \
    validation/r3-benchmark/exploratory/public-historical-v1/pre-execution-lock-v1
```

The output directory is created atomically and contains:

```text
manifest-integrity.json
pre-execution-lock.json
```

`manifest-integrity.json` is produced by the merged R3 benchmark integrity validator.
`pre-execution-lock.json` records SHA-256 digests for the manifest, materialization index,
review packet set, adjudications, and integrity evidence, plus the corpus identifier,
case count, protocol/plan versions, lock timestamp, and explicit
`product_execution_performed: false`.

## Scientific boundary

A successful lock means the corpus state is reproducibly frozen before product execution.
It does not establish detection quality or external validation. Any material change to
membership, artifacts, labels, or adjudications after first PermitDiff execution requires
a new corpus version rather than rewriting this lock.
