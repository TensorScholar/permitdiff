# R3 Closure Blocker Register

Register version: R3-CBR-v0.1-proposed

Document status: PROPOSED — requires Principal Systems Lead approval

Authority: No operational authorization granted

Evidence: No completed validation or operational evidence asserted

Scope: Discovery → Screening → Selection → Materialization → Review → Adjudication → Manifest → Lock → Execution → Results

## 1. Purpose and Historical Truth

This register proposes forward-looking governance definitions for the complete R3 pipeline:

Discovery → Screening → Selection → Materialization → Review → Adjudication → Manifest → Lock → Execution → Results

`docs/R3_FINAL_FREEZE_CLOSURE_AUDIT.md:22–26` originally recorded five undefined, unchecked “pending audit” placeholders. Forensic investigation confirmed that no historical definitions exist in repository history, commit messages, or the inspected PR context.

The definitions below are new prospective proposals, not recovered historical meanings. Approval of this register establishes their meaning going forward; it does not retroactively define or close the original placeholders.

### Historical placeholder mapping

| Historical placeholder | Proposed registry ID | Proposed responsibility |
|---|---|---|
| Blocker 1 | `R3-CB-01` | Discovery, screening, and selection integrity |
| Blocker 2 | `R3-CB-02` | Materialization and evidence provenance |
| Blocker 3 | `R3-CB-03` | Independent review, adjudication, and manifest integrity |
| Blocker 4 | `R3-CB-04` | Complete lock and controlled execution |
| Blocker 5 | `R3-CB-05` | Result completeness and canonical derivation |

Mapping status: Proposed until explicitly adopted. The original placeholder record remains historical evidence, not proof that these responsibilities were previously assigned.

## 2. Adoption Record Template

All fields remain unfilled until supported by an actual approval record.

| Field | Required entry |
|---|---|
| Register version | `<version>` |
| Approval authority | `<name, role, authority basis>` |
| Independent reviewer | `<name, role, independence declaration>` |
| Approval date | `<UTC timestamp>` |
| Approved commit | `<full SHA identifying the reviewed register and methodology>` |
| Tree identity | `<full Git tree object ID>` |
| Contract versions | `<contract inventory below>` |
| Placeholder mapping decision | `<explicit acceptance or amendments>` |
| Review evidence | `<immutable review reference>` |
| Approval decision | `<approved / changes required / rejected>` |
| Conditions and unresolved conflicts | `<recorded conditions or explicit none>` |
| Superseded register version | `<version or not applicable>` |
| Operational authorization | **None granted by register adoption** |

The approval record must reference an already identified commit/tree. A later record of approval must not silently substitute its own commit for the content that was reviewed.

### Contract inventory template

| Contract path | Version or schema identity | Source commit | Digest, where applicable | Precedence or resolved conflict |
|---|---|---|---|---|
| `<path>` | `<version>` | `<full SHA>` | `<digest>` | `<decision reference>` |

Record the frozen product-execution commit separately from the approved governance/methodology commit. Neither identity implicitly replaces the other.

Adoption approves definitions and review obligations only. It does not authorize discovery, corpus construction, reviewer assignment, execution, canonical result generation, or publication.

### Per-blocker ownership template

Ownership is recorded per blocker at adoption and on any ownership change. All values remain unfilled until explicitly assigned. Assignment of ownership does not close a blocker and does not authorize operational activity.

| Blocker | Blocker owner | Validation owner | Independent reviewer |
|---|---|---|---|
| `R3-CB-01` | `<unassigned>` | `<unassigned>` | `<unassigned>` |
| `R3-CB-02` | `<unassigned>` | `<unassigned>` | `<unassigned>` |
| `R3-CB-03` | `<unassigned>` | `<unassigned>` | `<unassigned>` |
| `R3-CB-04` | `<unassigned>` | `<unassigned>` | `<unassigned>` |
| `R3-CB-05` | `<unassigned>` | `<unassigned>` | `<unassigned>` |

- Blocker owner: accountable for evidence completeness and closure readiness for the assigned blocker.
- Validation owner: accountable for performing and recording the specified validation method and its limitations.
- Independent reviewer: accountable for the independent closure review, separate from evidence production and validation where independence is required.

## 3. Lifecycle and Decision Model

Each blocker maintains separate governance, readiness, operational-evidence, and closure states. A single “approved” checkbox is insufficient.

### 3.1 Governance approval

| State | Meaning |
|---|---|
| `PROPOSED` | Definition submitted; no adoption recorded |
| `UNDER_REVIEW` | Definition and source-contract mapping are being reviewed |
| `ADOPTED` | Authorized approval recorded against an exact version and identity |
| `CHANGES_REQUIRED` | Definition requires revision before adoption |
| `SUPERSEDED` | Replaced by an explicitly identified adopted version |

### 3.2 Readiness

| State | Meaning |
|---|---|
| `NOT_ASSESSED` | No readiness determination recorded |
| `IN_REVIEW` | Contracts, implementation coverage, procedures, and controlled-test evidence are under review |
| `GAPS_IDENTIFIED` | Unresolved prerequisites prevent readiness acceptance |
| `ACCEPTED` | Readiness requirements accepted for a specified phase and version |
| `STALE` | A relevant change invalidated the prior readiness assessment |

Readiness acceptance is not operational authorization or final closure.

### 3.3 Operational evidence

| State | Meaning |
|---|---|
| `NOT_ASSESSED` | No determination about operational evidence has been made |
| `AWAITING_AUTHORIZATION` | Evidence-generating activity cannot proceed under the recorded authority |
| `COLLECTING` | Evidence is being produced under a separately recorded authorization |
| `SUBMITTED` | Required evidence has been submitted for validation |
| `GAPS_IDENTIFIED` | Evidence is incomplete, inconsistent, or unsupported |
| `ACCEPTED` | Required evidence has passed the specified validation and review |
| `INVALIDATED` | Previously accepted evidence is no longer applicable or trustworthy |

### 3.4 Final closure

| State | Meaning |
|---|---|
| `OPEN` | Final closure has not been established |
| `UNDER_CLOSURE_REVIEW` | Adoption, readiness, evidence, and dependencies are being reconciled |
| `CLOSED` | Authorized independent closure decision is recorded |
| `REOPENED` | A change or invalidation requires renewed closure review |

Closure also records one disposition:

- `PROCEED_ELIGIBLE`: this blocker no longer prevents the next phase; separate authorization is still required.
- `STOP_REQUIRED`: the evidence establishes a contract-defined terminal stop; downstream progression remains prohibited.

Administrative closure of a stop disposition is not successful study readiness or scientific validation.

### Initial proposed states

For all five blockers:

```text
Governance: PROPOSED
Readiness: NOT_ASSESSED
Operational evidence: NOT_ASSESSED
Final closure: OPEN
Disposition: UNDETERMINED
```

These states make no claim that operational artifacts exist or are absent. No blocker is marked CLOSED.

## 4. Evidence and Authorization Rules

Every evidence submission must record:

- Artifact path or authoritative record reference.
- Immutable identity: commit, digest, or equivalent.
- Producer, timestamp, study version, and applicable phase.
- Validator identity, invocation, outcome, and coverage limitations.
- Independent reviewer and decision reference.
- Related authorization and dependency identities.

Schema-valid placeholders, synthetic fixtures, implementation inspection, or helper-function existence cannot substitute for actual operational evidence.

A separate phase-authorization record must identify the authority, permitted activity, scope, prerequisites, exact identities, and stop conditions. It must explicitly resolve any applicable prohibition in the existing closure audit before activity begins.

Changes to contracts, selection, labels, assignments, product identity, runtime, or accepted evidence require impact review. Affected readiness becomes `STALE`, evidence may become `INVALIDATED`, and closed dependent blockers become `REOPENED`.

---

## 5. Blocker Definitions

### R3-CB-01 — Discovery, Screening, and Selection Integrity

Purpose: Establish that the cohort follows the declared discovery frame and frozen screening, eligibility, ordering, cap, and shortfall rules without outcome-dependent selection.

Source contracts:

- `docs/r3-exploratory-corpus-plan.md`
- `docs/r3-discovery-harness.md`
- `docs/r3-screening.md`
- `docs/r3-pre-discovery-hardening.md`

Required readiness evidence:

- Approved search frame and completeness definition.
- Reconciled screening, eligibility, cap, minimum, and shortfall rules.
- Reviewed selection derivation and controlled tests for incomplete discovery, unresolved screening, caps, and shortfalls.

Required operational evidence:

- Discovery ledger and completeness/failure records.
- Screening decisions bound to the source ledger.
- Dispositions for all candidates requiring screening.
- Derived selection, exclusions, counts, and shortfall explanation.

Validation method:

- Validate schemas and source bindings.
- Independently recompute eligibility, ordering, caps, cohort membership, and viability.
- Review exclusion chronology and prohibited product-output influence.

Closure criteria:

- Declared-frame completeness is established without claiming ecosystem-wide completeness.
- Screening is resolved and recomputed selection matches.
- Exclusions and shortfalls follow the frozen contract.
- Nonviability produces `STOP_REQUIRED`, not permission to construct.

Dependencies:

- Adopted contract set and accepted discovery readiness.
- Separate authorization before discovery begins.
- No downstream product results may determine inclusion.

### R3-CB-02 — Materialization and Evidence Provenance

Purpose: Establish that retained evidence faithfully represents the authorized selection and immutable historical sources.

Source contracts:

- `docs/r3-public-materialization.md`
- `docs/r3-review-packets.md`
- `docs/r3-documentation-snapshot-manifest.schema.json`
- `docs/r3-pre-discovery-hardening.md`

Required readiness evidence:

- Reviewed materialization and retention procedures.
- Checks for membership, source identity, local containment, digests, and incomplete publication.
- Frozen selected-case failure/no-replacement policy.

Required operational evidence:

- Materialization index bound to selection.
- Repository, commit, blob, path, and retained-byte provenance.
- Artifact digests, immutable documentation, and applicable scenario evidence.
- Failure chronology and authorized dispositions.

Validation method:

- Reconcile selected and materialized membership and order.
- Verify retained bytes, historical-source correspondence, documentation snapshots, and artifact references.
- Review failures for unauthorized substitution or shrinkage.

Closure criteria:

- Every selected case has required evidence or an explicit contract-permitted failure disposition.
- No silent omissions, replacements, or cohort changes occurred.
- Evidence provenance is reproducible.
- Review inputs contain no prohibited product-derived annotations.
- Any progression-blocking failure remains a stop disposition.

Dependencies:

- `R3-CB-01` closed with `PROCEED_ELIGIBLE`.
- Accepted materialization readiness and separate phase authorization.

### R3-CB-03 — Independent Review, Adjudication, and Manifest Integrity

Purpose: Establish evidence-supported pre-execution labels and a manifest derived from independent review and traceable adjudication.

Source contracts:

- `docs/r3-review-packets.md`
- `docs/r3-adjudications.md`
- `docs/r3-reviewer-protocol.schema.json`
- `docs/r3-reviewer-roster.schema.json`
- `docs/r3-pre-discovery-hardening.md`
- `validation/r3-benchmark/exploratory/reviewer-protocol-v1.json`

Required readiness evidence:

- Separation of ground-truth adjudication from later comparative-review conditions.
- Approved eligibility, training, blinding, conflict, disagreement, and resolution procedures.
- Reviewed packet-to-adjudication-to-manifest derivation.

Required operational evidence:

- Digest-bound review packets and admissible context.
- Relevant reviewer qualifications, attestations, and exposure chronology.
- Independent decisions, disagreements, resolutions, and citations.
- Separate semantic relation, tool support, organizational intent, and resolution fields.
- Version-appropriate manifest bound to its source evidence.

Validation method:

- Validate bindings and reconcile case sets.
- Review independence and exposure records.
- Reproduce manifest content from adjudicated inputs.
- Use the applicable amended manifest schema rather than an obsolete default.

Closure criteria:

- Required decisions and resolutions exist for every case.
- Labels derive from admissible evidence, not product outcomes.
- Unsupported or unresolved cases follow frozen dispositions.
- Manifest content matches adjudication and provenance sources.
- Reviewer identifiers alone are not accepted as proof of independence.

Dependencies:

- `R3-CB-02` closed with `PROCEED_ELIGIBLE`.
- Accepted review readiness and separate review/adjudication authorization.
- Later comparative outcomes must not retroactively determine ground truth.

### R3-CB-04 — Complete Lock and Controlled Execution

Purpose: Bind study evidence and methodology to reproducible identities and establish that authorized execution used those identities.

Source contracts:

- `docs/r3-pre-execution-lock-v3.md`
- `docs/r3-freeze-completion.md`
- `docs/r3-pre-discovery-hardening.md`
- `docs/r3-execution-environment-lock.schema.json`
- `docs/r3-condition-assignment.schema.json`

Required readiness evidence:

- Reviewed v3 lock coverage and fail-closed behavior.
- Frozen commands, scenario handling, and change-control rules.
- Canonical assignment derivation.
- Product-build provenance, realized-runtime, and isolation verification procedures.

Required operational evidence before execution:

- Accepted v3 lock and immutable inputs.
- Distinct product and methodology identities.
- Eligible roster, reproducible assignment, and documentation bindings.
- Product-build provenance and realized-environment checks.
- Separate execution authorization referencing the accepted lock.

Required operational evidence after execution:

- Commands, timestamps, environment identities, exit states, output digests, and incidents.
- Required terminal dispositions for non-executed cases.

Validation method:

- Validate the complete lock and environment.
- Independently reproduce assignments and verify product provenance.
- Reconcile actual execution records against the authorized lock and frozen commands.

Closure criteria:

- V3 is accepted; v2 alone is insufficient.
- Required identities and evidence are bound.
- Execution contains no unexplained drift.
- Missing scenarios receive prescribed dispositions, including `NOT_EXECUTED_NO_PRIMARY_SCENARIO` where applicable.
- Deviations follow frozen invalidation rules.

Dependencies:

- Blockers 1–3 closed with `PROCEED_ELIGIBLE`.
- Separate authorization for applicable preparation activities and execution.

Execution subgate: Accepted pre-execution evidence plus separate execution authorization permits execution. Full Blocker 4 closure occurs afterward, avoiding a circular prerequisite.

### R3-CB-05 — Result Completeness and Canonical Derivation

Purpose: Establish that results are complete, lock-bound, derived from raw evidence, and interpreted under frozen rules.

Source contracts:

- `docs/r3-freeze-completion.md`
- `docs/r3-pre-discovery-hardening.md`
- `docs/r3-study-result-set.schema.json`
- Applicable freeze-completion record schemas

Required readiness evidence:

- Reviewed end-to-end validation coverage.
- Frozen denominators, invalidation, timing, metric, and interpretation rules.
- Controlled tests for incomplete, inconsistent, and unsupported analyses.

Required operational evidence:

- Required terminal records for every locked case and condition/channel.
- Immutable machine, baseline, and human-review evidence.
- Timing, disagreement, escalation, and invalidation records.
- Independently recomputed metrics and interpretation.
- Supplied-versus-derived comparison and claim review.

Validation method:

- Validate schemas and lock bindings.
- Reconcile record populations, terminal states, and referenced bytes.
- Derive denominators, metrics, timing, and interpretation from raw evidence.
- Compare the complete derived analysis against reported results.

Closure criteria:

- No unexplained missing, extra, duplicate, or contradictory records remain.
- Exclusions and invalidations follow frozen policy.
- Reported analysis matches canonical derivation.
- Claims respect inference-population and exploratory/confirmatory boundaries.
- Independent closure review accepts the derivation and limitations.

CB-05 closure does not equal publication approval, scientific conclusion approval, or external claim authorization. A separate results-release decision is still required before any publication, scientific conclusion, or external claim.

Dependencies:

- `R3-CB-04` closed with `PROCEED_ELIGIBLE`.
- Complete authorized study-condition evidence.
- Separate authorization for canonical result generation and publication where required.

## 6. Dependency Graph

```text
Register and contract-set adoption
                 |
Readiness acceptance + separate discovery authorization
                 |
CB-01: Discovery → Screening → Selection
                 |
CB-02: Materialization → Retained evidence
                 |
CB-03: Review → Adjudication → Manifest
                 |
CB-04: Accepted lock and realized-environment evidence
                 |
Separate execution authorization
                 |
Execution records → CB-04 final closure
                 |
CB-05: Complete records → Canonical derivation
                 |
Separate results-release decision
```

Each operational handoff additionally requires applicable readiness acceptance and separate phase authorization. A `STOP_REQUIRED` disposition halts downstream progression.

Readiness work may proceed in parallel. Accepted operational evidence cannot bypass unresolved upstream dependencies.

## 7. Risks and Controls

| Risk | Control |
|---|---|
| New definitions presented as historical intent | Explicit historical mapping and prospective adoption record |
| Governance approval mistaken for readiness or authorization | Separate lifecycle dimensions and authorization records |
| Circular evidence requirements | Distinguish pre-phase readiness, execution subgates, and post-phase closure |
| Synthetic or schema-valid artifacts mistaken for operational evidence | Record evidence class and require actual phase-specific artifacts |
| Product identity confused with governance HEAD | Separate immutable identities |
| Incomplete validator coverage treated as full enforcement | Document limitations and independently verify derivations |
| Outcome-driven exclusions or substitutions | Preserve chronology and frozen cohort/failure rules |
| Stale approvals after changes | Impact review, invalidation, and dependent reopening |
| Closure mistaken for empirical validation | Separate closure disposition, scientific findings, and publication authority |

This proposal defines governance obligations only. It records no adoption, completed evidence, blocker closure, or operational authorization.
