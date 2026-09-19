# R3 CB-01 corpus-construction amendment (prospective)

## Status

- **Scope:** PACKET A ONLY — prospective CB-01 corpus-construction amendment.
- **Adopted before:** real R3 discovery, real screening, real selection,
  real materialization, reviewer assignment, PermitDiff execution against
  R3 cases, pre-execution lock creation, R3 results, discovery
  authorization, readiness acceptance, and CB-01 closure.
- **Nature:** prospective only. This document is adopted before real R3
  discovery. It is not a reconstruction of historical intent.
- **Hardening-v1:** this amendment does not rewrite
  `validation/r3-benchmark/exploratory/pre-discovery-hardening-contract-v1.json`,
  `validation/r3-benchmark/exploratory/selection-plan.json`,
  `docs/r3-pre-discovery-hardening.md`, or
  `docs/r3-pre-discovery-hardening-contract.schema.json`.
- **Supersession:** this amendment supersedes earlier material only on the
  explicitly listed CB-01 discovery / lineage / count / publication
  subjects enumerated below. All other accepted methodology remains
  unchanged.
- **Authorization:** this amendment grants no operational authorization.
  It does not authorize discovery, screening, selection finalization,
  materialization, adjudication, condition assignment, locking, execution,
  or closure.
- **Machine source of truth:**
  `validation/r3-benchmark/exploratory/cb01-corpus-construction-contract-v1.json`
  validated by `docs/r3-cb01-corpus-construction-contract.schema.json`.
- **Deferred findings:** R3-MA-004, R3-MA-005, and R3-MA-006 are
  explicitly deferred to CB-03 / CB-04 and are not amended here.

## CB-01 subjects superseded

On these subjects only, this amendment controls over earlier exploratory
instructions:

1. raw public discovery ledger identity and producer binding (v2);
2. screening-decision byte binding and deterministic screened-ledger
   derivation (screened discovery v1);
3. canonical repository identity and repository-URL binding;
4. contamination re-derivation from the frozen contamination
   identity/register (stored `contamination_status` is never trusted);
5. selection-key and transition-ID formulas as frozen byte identities;
6. count definitions (`RAW_ELIGIBLE_COUNT`, `CAP_ADMISSIBLE_COUNT`,
   `SELECTED_CASE_COUNT`, `SHORTFALL`);
7. frozen target / cap / minimum and the below-minimum publication
   prohibition;
8. same-study-commit inheritance across one construction chain;
9. contract-digest binding via `SHA256(exact committed contract file bytes)`;
10. canonical artifact sequence and CB-01 construction-lineage evidence.

## Frozen counts

- **Target:** `18`.
- **Maximum cases per repository:** `2`.
- **Minimum viable selected natural slice:** `12`.

### RAW_ELIGIBLE_COUNT

All fully screened eligible cases before application of the repository
cap. This is transparency metadata only. It MUST NOT satisfy the 12-case
viability threshold by itself.

### CAP_ADMISSIBLE_COUNT

Number of cases surviving deterministic selection-key ordering plus the
frozen maximum of two cases per repository, computed before target
truncation. Procedure: sort every eligible screened transition by
`selection_key` ascending; scan the entire ordered set admitting at most
two cases per `repository_full_name`; the admitted sequence is
`CAP_SEQUENCE`; `CAP_ADMISSIBLE_COUNT = len(CAP_SEQUENCE)`.

### SELECTED

First 18 cases from the cap-admissible ordered sequence:
`SELECTED = CAP_SEQUENCE[:18]`.

### SELECTED_CASE_COUNT

`len(SELECTED)`.

### Viability

`SELECTED_CASE_COUNT >= 12`. Equivalent under `target = 18` to
`CAP_ADMISSIBLE_COUNT >= 12`.

### Shortfall

`18 - SELECTED_CASE_COUNT`.

### Below-minimum prohibition

A selection with `SELECTED_CASE_COUNT < 12` MUST NOT be finalized,
published, or materialized. The pure CB-01 constructor raises a dedicated
construction exception instead of returning a canonical selection payload.
This closes R3-MA-007 prospectively: a below-minimum selection can never
become finalizable evidence before a later validator rejects it.

## Canonical artifact sequence

The prospective canonical CB-01 construction chain is:

```text
raw public discovery v2
→ screening decisions v1
→ screened discovery v1
→ public selection v2
→ CB-01 construction lineage v1
→ public materialization v2
```

- Raw public discovery v2 originates `study_repository_commit`.
- Every derived artifact inherits the validated parent
  `study_repository_commit` and MUST NOT independently choose another
  commit. Operational Git-checkout enforcement arrives in Packet B;
  Packet A implements and tests only the semantic relationship.
- Every derived artifact binds its exact parent bytes via
  `SHA256(exact parent file bytes)`. Reserialized parsed JSON MUST NOT be
  substituted when original bytes are available.
- The CB-01 construction-lineage v1 artifact is deterministic technical
  integrity evidence only. It is NOT authorization. It contains no
  `generated_at` and no authorization semantics.
- Screened discovery v1, public selection v2, and lineage v1 contain no
  wall-clock `generated_at` field. The same inputs produce byte-stable
  outputs.

## Evidence-chain repairs (prospective)

- **R3-MA-001:** the screened ledger MUST be deterministically derived
  from the frozen raw discovery bytes plus byte-bound screening decisions.
  The screened artifact binds `SHA256(exact raw bytes)` and
  `SHA256(exact screening-decision bytes)`, and every pending transition
  must be decided exactly once.
- **R3-MA-002:** `contamination_status` MUST be re-derived from the frozen
  contamination identity/register in the machine contract. Stored
  `contamination_status` is validated but never trusted.
- **R3-MA-003:** `repository_full_name` is authoritative.
  `repository_url` MUST equal `https://github.com/<repository_full_name>`.
  The selection key is computed over the canonical URL, and any mismatch
  fails validation.
- **R3-MA-007:** see the below-minimum prohibition above.
- **R3-MA-008:** the canonical public producer identity is frozen in the
  machine contract and as a `const` in the raw public discovery v2
  schema. The lower-level non-public discovery producer emits no
  `producer_id` and therefore cannot produce a structurally valid v2
  artifact.
- **R3-MA-009:** viability uses `SELECTED_CASE_COUNT` /
  `CAP_ADMISSIBLE_COUNT`, never `RAW_ELIGIBLE_COUNT` alone.

## What this packet does not do

- Does not rewire `scripts/discover_r3_benchmark_candidates.py`,
  `scripts/discover_r3_public_benchmark_candidates.py`,
  `scripts/screen_r3_public_benchmark_candidates.py`, or
  `scripts/materialize_r3_public_selection.py`.
- Does not modify downstream R3 execution/review code, historical frozen
  contracts, or governance records listed in the Packet A brief.
- Does not run real discovery, contact GitHub, create real ledgers,
  selections, materializations, reviewer assignments, PermitDiff runs,
  locks, results, authorizations, or closures.
- Does not commit or push.
