# R3 review-trigger and scoring contract

## Status

**Contract:** `r3-review-trigger-scoring-v1`  
**Measurement contract:** `r3-exploratory-measurement-contract-v2`  
**Frozen:** before canonical exploratory adjudication and before PermitDiff execution on the
selected R3 corpus.

This contract defines how source-semantic ground truth maps to authorization-review
obligations and how PermitDiff case outcomes are normalized for exploratory scoring. It
does not redefine source semantics, tool support, organizational intent, or the source
semantics resolution dimension.

The machine-readable source of truth is the `review_trigger_scoring_contract` object in:

- `validation/r3-benchmark/exploratory/measurement-contract-v2.json`

The JSON Schema freezes that object exactly:

- `docs/r3-measurement-contract.schema.json`

## Ground-truth review classes

The directional relation is preserved exactly. No case is relabeled for scoring.

| Source relation | Review class |
| --- | --- |
| `WIDENING` | `REQUIRES_AUTHORIZATION_REVIEW` |
| `MIXED` | `REQUIRES_AUTHORIZATION_REVIEW` |
| `RESTRICTIVE` | `NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE` |
| `EQUIVALENT` | `NO_REVIEW_BY_SEMANTIC_DIRECTION_ALONE` |
| `UNRESOLVED` | `REQUIRES_SEMANTIC_ESCALATION` |

`MIXED` remains `MIXED`. By definition it contains established widening and restrictive
effects, so the widening component requires authorization review without converting the
ground-truth relation to `WIDENING`.

`RESTRICTIVE` and `EQUIVALENT` are not global "no review" claims. They mean only that the
semantic-direction rule defined for this benchmark does not itself require authorization
review.

`UNRESOLVED` is neither an ordinary positive nor an ordinary negative. It is a semantic
uncertainty class and requires escalation.

## Dimension independence

The following rules are frozen:

- `tool_support` never rewrites `source_semantic_relation`;
- `organizational_intent` never rewrites `source_semantic_relation`;
- organizational intent does not suppress the authorization-review trigger;
- an intentional widening can still require explicit authorization review/approval;
- `WIDENING` or `MIXED` remains in the overall known-review-required denominator when
  `tool_support` is `PARTIALLY_SUPPORTED` or `UNSUPPORTED`;
- a gate block caused only by unknown/unsupported/abstention is escalation, not a definite
  detection.

## Product disposition normalization

Each evaluated case receives exactly one product disposition:

- `DEFINITE_REVIEW_REQUIRED` — at least one definite authorization-widening or
  approval-weakening finding independently justifies review. Additional uncertainty does
  not erase that definite signal.
- `DEFINITE_NO_REVIEW_REQUIRED` — there is no definite review-triggering finding and no
  unresolved/unsupported condition requiring escalation; the measured construct may
  automatically pass.
- `ESCALATE` — there is no definite review-triggering finding, but uncertainty,
  unsupported semantics, abstention, or another fail-closed condition prevents automatic
  pass.

Normalization precedence is:

1. `DEFINITE_REVIEW_REQUIRED`
2. `ESCALATE`
3. `DEFINITE_NO_REVIEW_REQUIRED`

A case counts as a definite detection only when the definite review-triggering finding is
semantically correct under the frozen source ground truth. Blocking the case is not enough.

## Primary scoring populations

Define:

- known review-required population: `WIDENING` + `MIXED`;
- known no-review-by-direction population: `RESTRICTIVE` + `EQUIVALENT`;
- uncertain population: `UNRESOLVED`.

`UNRESOLVED` does not enter directional detection/error denominators. Its dispositions
remain visible in relation-stratified reporting, and it still contributes to operational
coverage/burden metrics.

## Metric definitions

### `definite_detection_recall`

Denominator: every known review-required case, including `PARTIALLY_SUPPORTED` and
`UNSUPPORTED` cases.

Numerator: denominator cases with disposition `DEFINITE_REVIEW_REQUIRED` and at least one
semantically correct definite review-triggering finding.

`ESCALATE` is not a detection.

### `automatic_pass_error_rate`

Denominator: every known review-required case, including `PARTIALLY_SUPPORTED` and
`UNSUPPORTED` cases.

Numerator: denominator cases with disposition `DEFINITE_NO_REVIEW_REQUIRED`.

### `decisive_coverage`

Denominator: all evaluated cases.

Numerator: cases classified as either `DEFINITE_REVIEW_REQUIRED` or
`DEFINITE_NO_REVIEW_REQUIRED`.

### `escalation_burden`

Denominator: all evaluated cases.

Numerator: cases classified as `ESCALATE`.

Under the normalization contract, `decisive_coverage` and `escalation_burden` are
complementary at the case level.

### `false_alarm_burden`

Denominator: `RESTRICTIVE` + `EQUIVALENT` cases.

Numerator: denominator cases classified `DEFINITE_REVIEW_REQUIRED` for the measured
authorization-widening construct.

An escalation is review effort, but it is not counted as a definite false alarm.

### `support_boundary_rate`

Denominator: all evaluated cases.

Numerator: cases with `tool_support` equal to `PARTIALLY_SUPPORTED` or `UNSUPPORTED`.

This measures applicability/support-boundary exposure, not source-semantic prevalence.

### `scenario_channel_availability`

Denominator: all evaluated cases.

Numerator: cases with a primary-admissible scenario channel under the frozen scenario
provenance contract. Explicit absence is not imputed. Task 4 defines how that provenance
is represented in the artifact chain.

### `static_channel_contribution`

Denominator: every known review-required case.

Numerator: denominator cases with a semantically correct definite review-triggering
finding from the static channel and no semantically correct definite review-triggering
finding from the primary-admissible scenario channel.

## Supported-subset view

The overall view is primary. It retains all known review-required cases regardless of
tool support.

A secondary supported-subset view filters to:

`tool_support == SUPPORTED`

The supported subset may recompute the outcome metrics listed in the machine contract, but
it must never replace the overall result or remove unsupported known widenings from the
headline denominator. `support_boundary_rate` remains an overall coverage descriptor.

## Rate reporting

For every rate:

- report numerator and denominator alongside the rate;
- if the denominator is zero, report the rate as `null`, not `0` or `1`;
- do not change mappings, denominators, or normalization rules after product outcomes are
  observed.

## Scientific boundary

This contract defines scoring semantics only. It does not execute PermitDiff, establish
benchmark performance, create external validation, or prove research novelty.
