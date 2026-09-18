# R3-CB-01 Adoption Review v1

## Status

Prospective governance review record for R3-CB-01 only.

No operational authorization granted. No blocker closed.

## 1. Historical boundary

- Existing "Blocker 1" in `docs/R3_FINAL_FREEZE_CLOSURE_AUDIT.md:22` was only an undefined placeholder (`pending audit`).
- This document creates a prospective mapping of that placeholder to `R3-CB-01`.
- No retrospective claim is made. This mapping does not assert that the definition existed historically.

## 2. Reference

- Register: `docs/R3_CLOSURE_BLOCKER_REGISTER.md`
- Register version: `R3-CBR-v0.1-proposed`
- Source commit SHA: `3b43b7321c4ed09bbc20b986e00a613e1a84d584`
- Source tree identity: `453f246190debce8ccb8faf3d4366f66f086935e`

## 3. Mapping

- Blocker 1 -> R3-CB-01 (prospective, under review).
- No mapping is made for CB-02 to CB-05 in this record. CB-02, CB-03, CB-04, and CB-05 remain unmapped by this document.

## 4. Contract inventory

All sources below exist at the referenced commit. No new contracts are introduced.

| path | version/schema identifier | commit SHA | role in CB-01 |
|---|---|---|---|
| `docs/r3-exploratory-corpus-plan.md` | `r3-exploratory-corpus-plan-v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Preregistered discovery, screening, selection, shortfall, and contamination rules |
| `docs/r3-discovery-harness.md` | implements `r3-exploratory-corpus-plan-v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Public-only collection, completeness controls, deterministic selection procedure |
| `docs/r3-screening.md` | operational handoff for `r3-exploratory-corpus-plan-v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Output-blind screening worksheet preparation and application |
| `docs/r3-public-selection.schema.json` | `permitdiff.dev/r3-public-selection/v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Machine contract for deterministic selection output |
| `docs/r3-discovery-ledger.schema.json` | `permitdiff.dev/r3-discovery-ledger/v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Machine contract for discovery ledger output |
| `docs/r3-screening-decisions.schema.json` | `permitdiff.dev/r3-screening-decisions/v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Machine contract for screening decisions bound to ledger bytes |
| `docs/r3-pre-discovery-hardening.md` | `r3-pre-discovery-hardening-v1` | `3b43b7321c4ed09bbc20b986e00a613e1a84d584` | Viability floor, no-replacement policy, and construction-ready gate |

## 5. Ownership

- Blocker owner: <unassigned>
- Validation owner: <unassigned>
- Independent reviewer: <unassigned>

## 6. Lifecycle state

- Governance: UNDER_REVIEW
- Readiness: IN_REVIEW
- Operational: AWAITING_AUTHORIZATION
- Closure: OPEN

## 7. Explicit prohibition

"This record does not authorize:
- discovery
- corpus construction
- screening
- selection
- materialization
- execution
- publication"

## 8. Open gaps

Unresolved items from the CB-01 audit. None are waived by this record.

- target/cap enforcement: selection entrypoints accept overrideable target/cap inputs; frozen 18/2 enforced downstream only.
- minimum enforcement: 12-case minimum and abort disposition live in the pre-discovery contract and v3 lock recomputation, not in the selector itself.
- provenance validation layering: selection copies artifact provenance verbatim and relies on screening to have rejected missing provenance.
- missing adversarial tests: shortfall>0 selection, contamination-path refusal, public select path, history-truncation incomplete, enumeration ordering, and non-default target/cap rejection lack dedicated coverage.
- construction readiness review: independent `R3_CORPUS_CONSTRUCTION_READY` review required by the hardening amendment has not been recorded.
