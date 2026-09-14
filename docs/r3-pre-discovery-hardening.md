# R3 pre-discovery hardening amendment

## Status

**Contract:** `r3-pre-discovery-hardening-v1`  
**Protocol:** `r3-benchmark-protocol-v1`  
**Measurement contract:** `r3-exploratory-measurement-contract-v2`  
**Freeze-completion contract:** `r3-freeze-completion-v1`  
**Adopted against:** `main@c3f3a866333f75ae3a1668177cda37c68aa05409`  
**Adopted before:** any new R3 public discovery, corpus construction, evaluated exposure, or product execution.

This amendment closes the remaining pre-result degrees of freedom identified by the independent post-PR-#51 freeze review. It does not construct the real R3 corpus, label a real case, execute PermitDiff against an R3 case, or create R3 results.

The machine-readable source of truth is:

`validation/r3-benchmark/exploratory/pre-discovery-hardening-contract-v1.json`

Its schema is:

`docs/r3-pre-discovery-hardening-contract.schema.json`

If this amendment conflicts with an earlier exploratory instruction on the specific topics below, this amendment controls. All accepted methodology not explicitly amended here remains unchanged.

## Natural-corpus viability

The public-historical natural slice keeps the preregistered **target of 18** and the **maximum of two selected cases per repository**.

The minimum viable natural slice is frozen at **12 selected cases**. This is an exploratory descriptive viability floor, not a statistical-power claim. It is fixed now, before discovery, as two thirds of the original 18-case target.

The action is deterministic:

- `eligible_count >= 18`: select exactly the first 18 cases under the frozen selection-key ordering and repository cap;
- `12 <= eligible_count < 18`: select every eligible case that survives the frozen repository cap and report the preregistered shortfall;
- `eligible_count < 12`: abort the corpus-construction attempt before materialization, adjudication, condition assignment, final locking, or product execution. A protocol amendment is required before another study version can proceed.

There is no later “looks large enough” judgment. `scripts/r3_pre_discovery_contract.py` is the executable construction gate, and the v3 pre-execution lock independently recomputes the deterministic selection from the screened ledger with target 18 and cap 2.

## Selected-case failure policy

Replacement is **not allowed** in the current corpus version.

Any selected-case pre-execution failure in the frozen failure vocabulary—provenance loss, artifact corruption, broken materialization, documentation-snapshot failure, invalid review packet, scenario-evidence integrity failure, or another pre-execution integrity failure—has one disposition:

`ABORT_CURRENT_CORPUS_VERSION_NO_REPLACEMENT`

The current corpus version may not shrink, substitute another case, or continue under a hand-edited selection. The failed case/reason and chronology must remain auditable, no label or product result may be consulted to make the decision, and a later attempt requires an explicitly new corpus-construction version. The v3 lock recomputes the selection from the frozen screened ledger, so discretionary substitution cannot lock successfully.

## Reviewer eligibility

The evaluated human comparison uses exactly three stable pseudonymous participants. Each participant must attest before assignment that they:

- can read JSON configuration diffs and reason about `permissions.defaultMode`, `allow`, `ask`, and `deny` changes;
- have working familiarity with Claude Code project settings and the frozen permission-semantics documentation supplied by the study;
- can distinguish widening, restriction/equivalence, and unresolved semantics without inventing undocumented runtime behavior.

Disqualifiers are frozen in `reviewer-protocol-v1.json`. In particular, a material contributor to PermitDiff product behavior at or after the frozen product commit is ineligible; the author/adjudicator of a specific case is ineligible for that case; prior case ground-truth exposure or PermitDiff-output exposure is disqualifying for that case; and a material unresolved conflict is disqualifying. Methodology-only contribution is not itself disqualifying.

The roster conforms to `docs/r3-reviewer-roster.schema.json` and is frozen before condition assignment.

## Reviewer training

Every participant receives the same frozen `r3-reviewer-training-v1` training exactly once before assignment or evaluated exposure:

- one field-orientation section covering the source permission fields, decision vocabulary, and PermitDiff report-field meanings without evaluated-case content;
- exactly three synthetic, disjoint worked examples: add-allow, remove-allow, and unresolved custom-matcher cases;
- answers and explanations are shown;
- frozen-procedure questions are allowed, but evaluated-case questions are prohibited before submission;
- maximum total training time is 45 minutes;
- all three worked examples and the orientation section must be completed;
- no evaluated case may be used for training;
- no training material may be added after evaluated behavior becomes visible.

Training does not differ by experimental condition.

## Condition assignment

The exact assignment version is `r3-condition-assignment-v1`, implemented by `scripts/r3_review_assignment.py`.

Inputs are the exact frozen case manifest, exact three-participant roster, and exact reviewer protocol. The assignment seed is:

`SHA256("r3-condition-assignment-v1\n" + manifest_sha256 + "\n" + roster_sha256)`

Cases and participants are separately ranked by SHA-256 with raw identifier ascending as the tie-breaker. For each case/participant cell:

`condition_index = (case_rank + participant_rank) mod 3`

with the ordered condition list:

1. `PERMITDIFF_ASSISTED`
2. `STRUCTURED_MANUAL`
3. `SOURCE_TEXT_DIFF`

With exactly three participants, every case receives exactly one reviewer in every condition; each participant sees a case in exactly one condition. Across cases, each participant's condition counts differ by at most one.

The entire assignment is generated before evaluated exposure. Before any exposure, participant dropout requires a new roster version and a complete reassignment. After any evaluated exposure, reassignment is forbidden; if dropout prevents a required terminal record, the study version is invalidated.

## Immutable source documentation

Live web content is not evidence during adjudication or evaluated review.

Every admissible documentation source must be captured into an immutable local snapshot manifest conforming to `docs/r3-documentation-snapshot-manifest.schema.json`. Each document records:

- source URL as provenance only;
- retrieval timestamp;
- retained snapshot path;
- exact SHA-256;
- content type and retained format;
- any normalization applied.

Each case records the ordered documentation-snapshot IDs and a canonical documentation-set digest. `scripts/r3_documentation_snapshots.py` verifies containment and content hashes. The same snapshot-set identity must be used for PermitDiff-assisted and structured-manual review. Source/text-diff review receives the same frozen documentation set but no full artifacts or scenarios, preserving the already declared secondary-baseline asymmetry.

The adjudication record must cite every case documentation snapshot using:

`documentation_snapshot:<document_id>:<snapshot_sha256>`

The v3 lock rejects adjudications that do not bind every frozen documentation snapshot. URL/title metadata in older packet structures is provenance only and must not be opened as live evidence during evaluated work.

## Scenario-channel cardinality

The configuration transition and scenario corpus remain separate experimental objects. The prior provenance rules are unchanged, with one additional deterministic cardinality rule needed by the singular frozen PermitDiff command:

- `primary_channel_state = ABSENT` requires zero primary-admissible scenario sets;
- `primary_channel_state = PRESENT` requires **exactly one** primary-admissible scenario set;
- more than one primary-admissible set fails the v3 lock and requires a protocol amendment before execution.

There is no operator choice among multiple primary-admissible sets after case evidence exists.

## Exact PermitDiff execution environment

The product remains frozen at:

`1f3b3a4afda67c01c4f29a93a45b18511980036b`

The reference runtime remains **CPython 3.13.15**. The R3 environment identity is now machine-readable in:

`validation/r3-benchmark/exploratory/permitdiff-execution-environment-v1.json`

It freezes Linux/amd64, the CPython 3.13.15 container base by OCI digest, exact direct/transitive runtime dependency versions, exact build dependency versions, SHA-256-authorized R3 copies of both dependency lockfiles, UTF-8, UTC, and execution with network disabled. The product is built from the exact frozen product commit and installed as a wheel; the exact realized wheel digest is bound by the v3 pre-execution lock.

`scripts/r3_execution_environment.py` verifies source-lock provenance, R3 lock digests, and—when invoked with `--validate-current`—the exact Python/platform/package realization. Environment drift fails closed.

## Result identity and completeness

All evaluated record contracts are versioned in `docs/r3-freeze-completion-records-v2.schema.json`. Every record is bound to the exact v3 pre-execution lock. PermitDiff records additionally bind the exact baseline/candidate hashes, primary scenario hash when present, product commit, product-wheel digest, environment-lock digest, command identity, and content-addressed outputs. Human records bind the case packet, documentation snapshot set, scenario evidence where shown, condition assignment, participant pseudonym, training version, and exact PermitDiff result for the assisted condition. Simple-baseline, invalidation, and disagreement records are likewise study-version bound.

`docs/r3-study-result-set.schema.json` requires one terminal state for every locked case in each required condition/channel. `scripts/r3_study_results.py` rejects missing, duplicate, extra, cross-study, or terminal-state-inconsistent records. In a valid study every required terminal state is `RECORDED`; after study invalidation, a not-yet-run condition must be explicitly represented as `NOT_RUN_STUDY_INVALIDATED` rather than silently disappearing.

## Arithmetic, timing, and primary metrics

Rates are never trusted as caller-supplied arithmetic. The scorer recomputes every rate from non-negative integer counts, requires numerator <= denominator, returns `null` only for a zero denominator, and rejects any supplied rate that differs from canonical recomputation.

The machine comparative result represents the full already-declared primary metric set:

- `definite_detection_recall`
- `automatic_pass_error_rate`
- `decisive_coverage`
- `escalation_burden`
- `false_alarm_burden`
- `support_boundary_rate`
- `scenario_channel_availability`
- `static_channel_contribution`

No new primary metric or composite score is introduced.

Human timing uses the fixed linear interpolation convention `h=(n-1)p` for Q1/median/Q3. One valid observation yields Q1=median=Q3=value and IQR=0. No valid observations yields null Q1, median, Q3, IQR, and total. Otherwise IQR is `Q3-Q1`. Median, IQR, and total are all represented in the machine result.

## Post-lock invalidation

The post-lock failure mapping is deterministic. `EXECUTION_FAILURE` is retained in the preregistered denominators as an execution failure. Every frozen provenance/evidence/environment/protocol-integrity failure invalidates the study version and produces no scoring result. Operator-selected denominator treatment is not permitted.

## Deterministic interpretation

`r3-primary-interpretation-v1` is unchanged. `scripts/r3_study_results.py` derives the outcome from validated raw evidence in the already frozen precedence:

1. `INVALIDATED`
2. `SAFETY_FAILURE`
3. `SUPPORTED`
4. `EFFORT_ADVANTAGE_ONLY`
5. `NO_MEANINGFUL_ADVANTAGE`
6. `MIXED_INCONCLUSIVE`

A supplied comparative analysis is accepted only if it exactly equals the canonical derivation. The result format cannot select `SUPPORTED`, or any other branch, contrary to the validated data.

## Final pre-execution lock v3

The prior v2 lock remains historically valid for its earlier scope but is **insufficient** for the amended R3 study. Before any R3 product execution, `permitdiff.dev/r3-pre-execution-lock/v3` is required.

The v3 lock reuses the v2 integrity validator as a prerequisite and then deterministically binds the screened ledger, exact selection, case evidence, immutable documentation snapshots, reviewer roster, condition assignment, execution environment, frozen product wheel, command identity, and every experiment-defining methodology component/validator by SHA-256. It also records the exact clean study-repository commit and per-case evidence bindings.

The same inputs produce the same v3 lock content; the v3 lock contains no wall-clock lock timestamp. Any changed bound input changes the final lock bytes/digest.

## Hard boundary

This amendment leaves the research state unchanged:

```text
R3_EXECUTION: NOT_STARTED
CANONICAL_R3_RESULTS: NOT_CREATED
EMPIRICAL_SCIENTIFIC_VALIDATION: 0%
EXTERNAL_VALIDATION_CLAIM: NOT_ESTABLISHED
```

This amendment does not itself authorize corpus construction. After merge and post-merge verification, an independent `R3_CORPUS_CONSTRUCTION_READY` review must decide whether construction may begin.
