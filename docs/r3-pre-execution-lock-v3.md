# R3 complete pre-execution evidence lock v3

## Status

**Lock schema:** `permitdiff.dev/r3-pre-execution-lock/v3`  
**Hardening contract:** `r3-pre-discovery-hardening-v1`  
**Product execution:** prohibited until this lock succeeds.

The v3 lock is the complete pre-result cryptographic boundary for the amended R3 study. It supersedes v2 as the required execution gate; v2 is retained and reused as an integrity-validation prerequisite.

## Deterministic bound state

The lock binds, by SHA-256 or exact Git identity:

- screened discovery ledger and deterministic selection;
- manifest, materialization, blinded review packets, adjudications, and scenario channels;
- immutable documentation-snapshot manifest and per-case snapshot-set identities;
- exact three-person reviewer roster and condition assignment;
- exact R3 execution-environment lock and hash-locked dependency snapshots;
- exact frozen PermitDiff product wheel and product commit;
- frozen PermitDiff command/configuration identity;
- per-case baseline/candidate, review-packet, documentation, scenario, and adjudication identities;
- the exact clean Git commit containing the study methodology;
- every listed methodology contract, schema, construction validator, scoring validator, simple baseline implementation, and lock implementation that can affect inclusion, evidence, denominators, invalidation, scoring, or top-level interpretation.

The output intentionally has no generated timestamp. With identical bound inputs and the same clean Git commit, its bytes are deterministic.

## Additional closure checks

Before writing the lock, the implementation:

- re-runs the complete v2 pre-execution validator in a temporary directory;
- recomputes the natural selection from the screened ledger with target 18 and repository cap 2;
- refuses fewer than 12 natural cases;
- rejects any materialization membership/order that differs from the deterministic selection;
- rejects any current-version selected-case substitution;
- requires every documentation snapshot and digest to validate;
- requires every adjudication to cite the exact frozen documentation snapshots;
- requires the assignment to match the exact manifest, roster, reviewer protocol, and deterministic ranking;
- requires `PRESENT` scenario channels to contain exactly one primary-admissible scenario set and `ABSENT` to contain none;
- validates the execution-environment lock and product-commit dependency-lock provenance;
- requires a clean Git worktree and verifies every bound methodology component exactly matches the recorded HEAD.

## Invocation

The real paths are intentionally supplied only after corpus construction and independent authorization. A representative form is:

```text
python scripts/lock_r3_exploratory_corpus_v3.py \
  --screened-ledger <screened-ledger.json> \
  --selection <public-selection.json> \
  --manifest <manifest.json> \
  --materialization <materialization.json> \
  --review-packets <review-packets.json> \
  --adjudications <adjudications-v2.json> \
  --scenario-channels <scenario-channels-v1.json> \
  --documentation-snapshots <documentation-snapshots.json> \
  --reviewer-roster <reviewer-roster.json> \
  --condition-assignment <condition-assignment.json> \
  --product-wheel <permitdiff-wheel.whl> \
  --output <pre-execution-lock-v3.json>
```

This command performs validation and locking only. It does not execute PermitDiff or create benchmark results.
