# R3 measurement-contract amendment

## Status

**Amendment ID:** `r3-exploratory-measurement-amendment-2026-09-12-v1`  
**Measurement contract:** `r3-exploratory-measurement-contract-v2`  
**Parent plan:** `r3-exploratory-corpus-plan-v1`  
**Protocol:** `r3-benchmark-protocol-v1`  
**Adopted:** 2026-09-12, before any canonical Slice A labels and before any PermitDiff execution on the selected exploratory corpus.

This is a transparent pre-execution amendment prompted by an independent one-shot strategic/research review. The review identified construct-validity risks in the original adjudication vocabulary, scenario provenance, abstention scoring, and human-baseline independence.

The amendment changes **measurement and adjudication interpretation only**. It does not alter the frozen discovery queries, candidate paths, public-only boundary, exclusion vocabulary, contamination register, deterministic selection algorithm, per-repository cap, or no-product-output-before-lock rule.

## Why this amendment is necessary

The original three-way review label combined several distinct questions:

- what the source-system authorization semantics changed;
- whether the change was organizationally intended;
- whether PermitDiff supports the relevant semantics;
- whether the source semantics themselves are resolvable from public evidence.

That conflation can make evaluation circular. A source-level widening remains a widening even when PermitDiff cannot analyze it. Likewise, an intentional widening may still require explicit authorization review without being a historical security defect.

The exploratory study therefore separates these dimensions before labels or product outputs exist.

## Frozen source-semantic ground truth

Each selected natural-history case must record exactly one `source_semantic_relation`:

- `WIDENING` — documented source semantics establish a net authorization broadening or approval-boundary weakening relevant to the frozen review scope;
- `RESTRICTIVE` — documented source semantics establish a net restriction;
- `EQUIVALENT` — the changed authorization-relevant source state is semantically equivalent within the frozen scope;
- `MIXED` — both widening and restrictive effects are established and a single directional ordering would be misleading;
- `UNRESOLVED` — available public source evidence cannot establish the source-level relation without undocumented runtime/precedence/environment assumptions.

`UNRESOLVED` is a statement about source-semantic ground truth. It is **not** a synonym for PermitDiff unsupported behavior.

Atomic semantic categories remain allowed as explanatory metadata. They do not replace the source-level relation.

## Tool support is a separate dimension

Each case must separately record `tool_support`:

- `SUPPORTED`;
- `PARTIALLY_SUPPORTED`;
- `UNSUPPORTED`.

A known `WIDENING` case remains in the widening denominator even if PermitDiff is `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, or abstains. Tool support must not redefine ground truth.

## Organizational intent is a separate dimension

Each case must separately record `organizational_intent`:

- `KNOWN_INTENDED`;
- `KNOWN_UNINTENDED`;
- `UNAVAILABLE`;
- `NOT_APPLICABLE`.

For public historical repositories, intent is normally `UNAVAILABLE` unless independent public evidence establishes it. The study must not infer intent from the configuration diff or from PermitDiff output.

The primary natural-history research target is therefore **review-worthy authorization widening / approval-boundary weakening**, not retrospective proof that a historical commit was a security vulnerability.

## Source-semantic resolution

Each case records `source_semantics_resolution`:

- `RESOLVED`;
- `AMBIGUOUS`;
- `UNAVAILABLE`.

A `source_semantic_relation` other than `UNRESOLVED` requires `RESOLVED` source semantics under the frozen evidence set.

## Exploratory semantic-version policy

The exploratory public-historical slice uses **fixed-version semantic replay**, not a claim about historical deployed runtime behavior.

Before adjudication, the allowed source-system documentation set and its version/date context must be frozen in the review context. Labels answer:

> Under the frozen documented source semantics and declared review assumptions, what semantic relation holds between the exact baseline and candidate artifacts?

The study must not claim that current documentation proves the behavior of the vendor runtime at the historical commit date.

A later confirmatory study may choose contemporaneous historical reconstruction, but only if reliable versioned semantic evidence exists and that policy is preregistered.

## Scenario provenance contract

The benchmark configuration transition and the PermitDiff scenario corpus are distinct experimental objects.

Every scenario set used for evaluation must record one provenance class:

- `PREEXISTING_PROJECT` — existed independently of this benchmark before case adjudication;
- `INDEPENDENT_BLIND` — authored without access to PermitDiff output and without access to the case ground-truth decision;
- `DIAGNOSTIC_ANSWER_INFORMED` — authored with knowledge of the expected semantic relation or specifically to witness it;
- `PRODUCT_GENERATED` — produced by PermitDiff or a PermitDiff-coupled generator.

Only `PREEXISTING_PROJECT` and properly controlled `INDEPENDENT_BLIND` scenarios may support the primary comparison of ordinary review effectiveness.

`DIAGNOSTIC_ANSWER_INFORMED` scenarios are permitted for debugging and mechanism analysis, but their results must be reported separately and must not be presented as evidence that an ordinary pre-existing corpus would have caught the change.

`PRODUCT_GENERATED` scenarios, if introduced later, are part of the evaluated method and their generation cost must be counted.

If a public historical case has no admissible scenario corpus, the observed-scenario channel is reported as absent for that case. The benchmark must not fabricate answer-informed scenarios merely to make the observed channel succeed.

## Abstention and fail-closed scoring

Ground truth and release handling are scored separately.

For independently known `WIDENING` cases:

- a definite correct widening finding counts as a detection;
- an abstention / unsupported / unknown result does **not** count as a true-positive detection merely because the gate blocks;
- an automatic pass without required review is an automatic-pass error;
- an escalation is reported in the escalation-burden metric.

The exploratory report must therefore separate at least:

- definite detection recall;
- automatic-pass error rate;
- decisive coverage;
- escalation burden;
- false-alarm burden;
- support-boundary rate;
- scenario-channel availability;
- static-channel contribution.

A system that blocks every case cannot claim perfect detection from containment alone.

## Human-review independence

Ground-truth adjudicators and timed comparison reviewers are different experimental roles.

For any confirmatory human-review comparison:

- an adjudicator who studied a case to establish ground truth must not be treated as an uncontaminated timed baseline reviewer for that same case;
- each study participant sees a given case in only one experimental condition;
- condition assignment is balanced across participants and cases;
- training cases are disjoint from evaluated cases;
- the structured-review checklist is frozen before evaluated case exposure.

Exploratory single-review adjudication remains allowed under the parent plan, but exploratory reviewer-time claims are descriptive unless independence is preserved.

## Holdout and contamination rule

A case or repository family that has been inspected for product debugging is not fresh confirmatory evidence later merely because its corpus version or digest changes.

Product fixes triggered by exploratory evidence require genuinely fresh confirmatory material for an output-independent validation claim.

The exposure/contamination register therefore covers not only prior product execution, but also material developer access to held-out case content or labels.

## Baseline contract

The primary product-value comparison is **PermitDiff-assisted review versus structured manual review**.

The exploratory design should additionally include, where semantically honest and reproducible:

- plain/source diff review;
- a simple native configuration-change checker;
- scenario-only ablation;
- static-only ablation.

External analyzers are executable baselines only where a faithful semantic overlap exists. Prior art can constrain novelty without being forced into an invalid benchmark translation.

## What remains unchanged

This amendment does not change:

- Slice A target of up to 18 selected public historical transitions;
- maximum two selected cases per repository;
- fixed discovery concepts and exact candidate paths;
- fixed screening/exclusion vocabulary;
- deterministic SHA-256 selection key;
- preservation of excluded and non-selected candidates;
- public-only collection;
- output-blind selection and adjudication;
- no PermitDiff execution before the pre-execution lock;
- exploratory results remaining non-confirmatory.

## Tooling consequence

The staging adjudication/review-packet tooling created before this amendment uses the earlier conflated label contract. It must **not** be used to freeze canonical exploratory labels until it is updated to conform to this amendment and receives exact-head executable validation.

The pre-execution lock must ultimately bind the machine-readable measurement contract so that later execution cannot silently revert to the superseded interpretation.

## Scientific boundary

This amendment improves construct validity; it does not create external validation, accuracy evidence, or research novelty.
