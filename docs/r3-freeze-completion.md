# R3 freeze-completion contract

## Status

**Contract:** `r3-freeze-completion-v1`  
**Protocol:** `r3-benchmark-protocol-v1`  
**Measurement contract:** `r3-exploratory-measurement-contract-v2`  
**Scientific baseline product commit:** `1f3b3a4afda67c01c4f29a93a45b18511980036b`

This document freezes the remaining pre-result experimental degrees of freedom identified by the R3 execution-readiness review. It does not construct the real corpus, label any real case, execute PermitDiff against an R3 case, or create R3 results.

The machine-readable source of truth is:

`validation/r3-benchmark/exploratory/freeze-completion-contract-v1.json`

Its schema is:

`docs/r3-freeze-completion-contract.schema.json`

## Primary inference boundary

The primary comparative inference is the natural `public_historical` slice only. Synthetic or unsupported/stress material is secondary diagnostic/coverage evidence. Synthetic or stress cases cannot rescue, overturn, or strengthen a weak natural-corpus primary result.

Once the natural corpus is frozen, no case may silently disappear. Any post-freeze integrity or execution failure follows the invalidation/change-control contract below.

## Structured manual-review comparator

The exact comparator is `r3-structured-manual-review-v1`.

The reviewer receives exactly:

- exact baseline artifact;
- exact candidate artifact;
- plain unified source diff;
- immutable provenance;
- the frozen source-documentation references for the case;
- the same primary-admissible scenario set available to the PermitDiff-assisted condition, when one exists.

No open-web or case-specific evidence outside the frozen documentation set is allowed. Ground truth, PermitDiff output, other reviewers' decisions, and post-hoc explanations are hidden.

The reviewer performs this checklist in order:

1. Verify case identifier, provenance, and baseline/candidate digests.
2. Inspect the exact artifacts, plain diff, and only frozen source documentation.
3. Identify changes to `permissions.defaultMode`, `permissions.allow`, `permissions.ask`, `permissions.deny`, and documented semantics material to the frozen authorization-review scope.
4. Decide whether the change establishes widening/approval weakening, establishes only restriction/equivalence, or cannot be resolved without undocumented assumptions.
5. If a primary-admissible scenario set is present, inspect it as declared review context. Never invent scenarios; scenario absence is not safety evidence.
6. Submit one decision, one confidence score, rationale, and uncertainty notes before stopping.

Decision vocabulary is exactly:

- `REQUIRES_AUTHORIZATION_REVIEW`
- `NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE`
- `REQUIRES_SEMANTIC_ESCALATION`

Confidence is integer 1–5. Unresolvable semantics require escalation rather than guessing.

Timing starts immediately before any case evidence is displayed. Timing stops on final submission. An interruption over 60 seconds makes timing invalid but leaves the decision usable. The active-review ceiling is 1200 seconds; at the ceiling an undecided reviewer must escalate. No post-submit edits belong to the timed condition.

Case order is deterministic per participant: sort assigned cases by SHA-256 of:

`r3-review-order-v1 + "\n" + participant_id + "\n" + case_id + "\n" + condition`

Each participant sees a given case in exactly one condition. Condition assignment must be balanced before evaluated exposure. Ground-truth adjudicators cannot act as uncontaminated timed reviewers for the same case.

Records conform to `docs/r3-freeze-completion-records.schema.json#/$defs/humanReviewRecord`.

## Source/text-diff review

This is a secondary minimum-review baseline. The reviewer receives only the plain source diff, immutable provenance, and the same frozen source documentation. Full artifacts, scenarios, and PermitDiff output are intentionally withheld. This asymmetry is an explicit experimental variable and is not the primary comparator.

It uses the same decision vocabulary, timing rules, blinding rules, and output schema.

## Simple automated baseline

The exact implementation is:

`scripts/r3_simple_native_baseline.py`

Version: `r3-simple-native-change-checker-v1`.

It receives only exact baseline/candidate Claude Code project-settings JSON. It has no scenarios, source documentation, labels, or PermitDiff output.

Algorithm:

1. Parse both files as JSON objects and require `permissions` objects.
2. Require `permissions.defaultMode == "dontAsk"` in both; otherwise return `UNKNOWN`.
3. Treat missing `allow`, `ask`, or `deny` as empty arrays; present values must be string arrays.
4. Compare `allow` as exact raw-string sets without semantic subsumption.
5. Any candidate-only raw allow entry returns `REVIEW_REQUIRED`.
6. Any exact-array change to `ask` or `deny` returns `REVIEW_REQUIRED`.
7. If only allow entries are removed, or no relevant array changes, return `NO_REVIEW_REQUIRED`.
8. Unsupported valid shapes return `UNKNOWN`; invalid JSON returns `ERROR`.

Mapping is frozen:

- `REVIEW_REQUIRED` -> `DEFINITE_REVIEW_REQUIRED`
- `NO_REVIEW_REQUIRED` -> `DEFINITE_NO_REVIEW_REQUIRED`
- `UNKNOWN` -> `ESCALATE`
- `ERROR` -> `ESCALATE`

Output conforms to `docs/r3-freeze-completion-records.schema.json#/$defs/simpleBaselineResult`.

## Evidence-access parity

The authoritative matrix is embedded in the machine contract.

The primary human comparison is PermitDiff-assisted review versus structured manual review. These two conditions receive identical human-readable source evidence and identical primary-admissible scenario material when present. The only intended difference is that the assisted condition additionally receives the frozen PermitDiff JSON report and Claude projection-evidence JSON.

Ground-truth/adjudication material is unavailable to every evaluated condition.

The source/text-diff and simple automated baselines intentionally receive less evidence and are secondary baselines. Their asymmetry is explicit and cannot be reinterpreted as a PermitDiff advantage.

## PermitDiff execution identity

The evaluated product commit is exactly:

`1f3b3a4afda67c01c4f29a93a45b18511980036b`

For a case whose scenario registry records a primary-admissible scenario channel as `PRESENT`, the exact command is:

```text
python -m permitdiff claude compare {baseline_path} {candidate_path} {primary_scenario_path} --strict --format json --output {permitdiff_report_path} --evidence-output {projection_evidence_path}
```

`--allow-ignored-root-changes` and `--acknowledge-webfetch-sandbox-gap` remain false. No benchmark-specific hidden configuration is permitted.

The reference runtime is CPython 3.13.15, UTF-8, UTC timestamps, and no execution-time network dependency.

If the scenario registry records `ABSENT`, the study does **not** fabricate a scenario and does not invoke the scenario-dependent product command. It emits the execution state `NOT_EXECUTED_NO_PRIMARY_SCENARIO`, maps the product disposition to `ESCALATE`, and retains the case in predeclared denominators. This is conservative by design and prevents scenario availability from being repaired after labels are known.

The assisted reviewer sees the same structured-manual evidence plus the raw frozen-command JSON report and raw projection evidence. No ground truth or answer-informed explanation may be added.

Machine result records conform to `docs/r3-freeze-completion-records.schema.json#/$defs/permitdiffResultRecord`.

## Severity policy

R3 uses approach B: severity is descriptive and non-primary only.

PermitDiff-emitted severity may be preserved verbatim in raw product output. R3 does not define or infer an independent severity taxonomy for the primary analysis.

Severity is prohibited from affecting corpus membership, primary scoring, case weighting, headline claims, top-level interpretation, or post-result case selection.

## Raw result and disagreement schemas

The frozen schemas are:

- `docs/r3-freeze-completion-records.schema.json#/$defs/permitdiffResultRecord`
- `docs/r3-freeze-completion-records.schema.json#/$defs/humanReviewRecord`
- `docs/r3-freeze-completion-records.schema.json#/$defs/simpleBaselineResult`
- `docs/r3-freeze-completion-records.schema.json#/$defs/invalidationRecord`
- `docs/r3-freeze-completion-records.schema.json#/$defs/reviewDisagreementRecord`
- `docs/r3-freeze-completion-records.schema.json#/$defs/comparativeAnalysisResult`
- existing ground-truth schema `docs/r3-adjudications.schema.json`

No actual result files are created by this freeze-completion change.

## Post-freeze invalidation and change control

Any frozen-case failure must create a record conforming to `docs/r3-freeze-completion-records.schema.json#/$defs/invalidationRecord`.

Execution failures and resolvable uncertainty remain visible and remain in predeclared denominators. A provenance/evidence failure that invalidates the frozen review unit invalidates the study version rather than deleting the case from scoring.

Every record preserves original repository/path/commit/digest identity, failure reason, chronology, denominator treatment, authorization, and `outcome_consulted=false`.

Outcome-dependent exclusion is forbidden.

## Comparative endpoints

The primary population is the natural public-historical slice only. No composite score is permitted.

Consequential ground truth is `WIDENING + MIXED`. Negative directional ground truth is `RESTRICTIVE + EQUIVALENT`. `UNRESOLVED` remains separate.

The machine contract freezes these endpoints separately:

- consequential changes detected;
- missed consequential changes;
- false/misleading alerts;
- definite-detection recall;
- automatic-pass error rate;
- decisive coverage;
- UNKNOWN/escalation burden;
- false-alarm burden;
- review effort;
- review time where timing is valid;
- agreement/disagreement with the adjudicated reference;
- unsupported-case handling.

Unsupported/partially supported known widenings remain in overall positive denominators. Escalation is not detection. An automatic pass on a known widening/mixed case is an error. Zero denominators produce `null` rates.

Review-time summaries are median, IQR, and total active seconds. An effort-only top-level claim is unavailable unless all natural cases required by the compared human conditions have valid timing.

## Top-level interpretation

The deterministic interpretation contract is `r3-primary-interpretation-v1`.

Precedence is:

1. `INVALIDATED`
2. `SAFETY_FAILURE`
3. `SUPPORTED`
4. `EFFORT_ADVANTAGE_ONLY`
5. `NO_MEANINGFUL_ADVANTAGE`
6. `MIXED_INCONCLUSIVE`

Rules are frozen in the machine contract.

In summary:

- any study-version invalidation => `INVALIDATED`;
- any natural-case automatic-pass error => `SAFETY_FAILURE`;
- `SUPPORTED` requires lower assisted missed-consequential-change count than structured manual, no higher assisted false/misleading alerts, PermitDiff escalation burden at or below one third, and PermitDiff definite-detection recall above the simple automated baseline;
- `EFFORT_ADVANTAGE_ONLY` requires equal missed-consequential-change count, no higher false alerts/escalations, all timing valid, and at least 20% reduction in both median and total active review time;
- no qualifying detection or effort advantage under the burden guard => `NO_MEANINGFUL_ADVANTAGE`;
- excessive escalation, missing required denominators, invalid effort timing, or conflicting advantages/burdens => `MIXED_INCONCLUSIVE`.

Synthetic/stress outcomes may never select or upgrade the primary interpretation.

## Hard boundary

This contract leaves the following states unchanged:

```text
R3_EXECUTION: NOT_STARTED
CANONICAL_R3_RESULTS: NOT_CREATED
EMPIRICAL_SCIENTIFIC_VALIDATION: 0%
EXTERNAL_VALIDATION_CLAIM: NOT_ESTABLISHED
```

The next permissible activity after merge and a fresh freeze review is natural-corpus construction under the already frozen discovery/screening/materialization/adjudication/lock pipeline. This file itself does not authorize that activity.
