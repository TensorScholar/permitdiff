# PermitDiff R3 External Benchmark Protocol

## Status

**Protocol status:** frozen before confirmatory benchmark execution.

This document defines the scientific and engineering protocol for evaluating PermitDiff against independent ground truth and comparison baselines. It is intentionally written before confirmatory results are collected so that the benchmark cannot be silently tuned around observed outcomes.

This protocol does **not** upgrade PermitDiff beyond `ENGINEERING VERIFIED`. A maturity upgrade requires confirmatory evidence produced under this protocol and reviewed against the claim boundaries below.

## Objective

Evaluate whether PermitDiff improves release-time detection of authorization regressions over simpler review methods within the policy semantics and adapter projections PermitDiff explicitly supports.

The benchmark is designed to answer five questions:

1. How reliably does PermitDiff detect supported authorization broadening and approval-boundary regressions?
2. How often does PermitDiff report a security-relevant finding when the adjudicated case is benign?
3. How often does PermitDiff refuse to make a safe claim and return an unsupported/unknown result?
4. How does PermitDiff compare with plain text diff and structured manual review for reviewer effort and detection quality?
5. Which error modes are attributable to implementation defects, unsupported semantics, ambiguous source-system behavior, or benchmark-label uncertainty?

## Claim boundary

The benchmark may support claims about:

- supported semantic permission-change classes;
- observed corpus transitions for supplied scenarios;
- bounded static declared-authority analysis;
- fail-closed unknown handling;
- deterministic release gating and evidence generation;
- reviewer burden on the benchmarked cases.

The benchmark must **not** be used to claim:

- exhaustive authorization safety;
- complete global reachability or effective-authority analysis;
- perfect semantic equivalence across arbitrary authorization systems;
- runtime authorization safety;
- production security guarantees;
- performance on ecosystems not represented by a documented supported adapter/projection;
- commercial adoption or production validation.

## Benchmark unit

A benchmark case is one immutable authorization-change review unit containing:

- a baseline policy/configuration artifact;
- a candidate policy/configuration artifact;
- adapter/source-system identity when applicable;
- the exact source commit or artifact digest for both states;
- any review corpus/scenarios required by the PermitDiff analysis path;
- an adjudicated semantic label;
- adjudication rationale and evidence;
- the expected supported/unsupported boundary;
- metadata describing the change family.

One case may contain multiple raw textual edits, but it must have one review-level ground-truth outcome. Multi-effect cases must also record atomic sublabels so aggregate metrics do not hide partial failures.

## Case taxonomy

The corpus should contain both positive and negative cases. At minimum, the confirmatory set must represent the following classes where supported by the current product:

### Security-relevant positive classes

- new `ALLOW` authority;
- approval bypass or `REQUIRE_APPROVAL` to `ALLOW` relaxation;
- deny/removal or restrictive-rule removal;
- tool/scope addition;
- predicate removal;
- numeric bound relaxation;
- default-effect relaxation;
- static declared-authority expansion;
- precedence/order changes that may widen first-match behavior within the implemented model;
- candidate-rule coverage gaps that strict review should reject;
- missing differential evidence where the strict gate requires it;
- stale or mismatched waiver/evidence binding;
- supported native-adapter projection-gap conditions that require explicit evidence handling.

### Benign / negative classes

- authority contraction;
- additional restrictions;
- approval strengthening;
- deny additions;
- scope narrowing;
- predicate tightening;
- numeric bound tightening;
- equivalent normalization changes;
- formatting/comment-only changes when the source format permits them;
- unrelated configuration changes outside the supported authorization projection, provided the adapter is expected to fail closed or explicitly classify them according to its contract.

### Unknown / unsupported classes

The corpus must deliberately include cases that the bounded model cannot soundly order. Examples include unsupported predicate relations, ambiguous glob relations, unmodeled source-system semantics, or precedence interactions for which disjointness cannot be established.

These cases are not automatically false positives. They are scored separately as unknown/unsupported handling and become errors only when PermitDiff makes a stronger safe/unsafe claim than its documented model justifies.

## Corpus construction

### Sources

Cases may come from:

- public repository history;
- public issue or pull-request examples;
- public policy/configuration fixtures;
- purpose-built synthetic cases used only to cover otherwise missing atomic semantics.

Public historical cases are preferred for external-validity evidence. Synthetic cases are allowed for coverage but must be labeled synthetic and reported separately from historical/public results.

### Inclusion criteria

A case may enter the confirmatory corpus only if:

1. both baseline and candidate artifacts are immutable and reproducibly retrievable or vendored with provenance;
2. the authorization semantics relevant to the label can be adjudicated without consulting PermitDiff output;
3. the case maps to a documented PermitDiff support boundary or is intentionally included as an unsupported/unknown control;
4. the case contains enough evidence for a second reviewer to reproduce the label;
5. no private/customer data is required.

### Exclusion criteria

Exclude from confirmatory scoring:

- cases whose ground truth depends on undocumented runtime state unavailable to reviewers;
- cases with unresolved source provenance;
- cases whose label changed because PermitDiff output influenced the adjudicator;
- cases added after confirmatory execution began solely to improve a metric;
- duplicate cases that differ only cosmetically unless duplication is intentional and reported as a robustness slice.

## Exploratory and confirmatory split

The benchmark has two strictly separated phases.

### Exploratory set

Used to:

- debug the harness;
- refine case schemas;
- discover product defects;
- clarify label definitions;
- identify unsupported semantics;
- improve documentation and diagnostics.

PermitDiff may be changed in response to exploratory findings. Exploratory results are not used as final evidence of detection quality.

### Confirmatory set

Used only after the following are frozen:

- case list and case IDs;
- baseline/candidate artifacts and digests;
- labels and adjudication records;
- PermitDiff version/commit;
- baseline tool versions/configuration;
- metric definitions;
- scoring code;
- exclusion policy.

No behavior-affecting PermitDiff changes, threshold changes, case relabeling, or case replacement may occur after confirmatory execution begins. If a defect is discovered, the run is preserved, the defect is fixed in a later version, and a new benchmark version is created.

## Ground-truth adjudication

Ground truth must be established independently of PermitDiff output.

### Label schema

Each case receives:

- `SECURITY_RELEVANT_REGRESSION`
- `BENIGN_OR_RESTRICTIVE_CHANGE`
- `UNKNOWN_OR_UNSUPPORTED`

Positive cases additionally record one or more atomic semantic categories from the case taxonomy.

### Review process

For confirmatory cases:

1. Reviewer A labels the case from source artifacts and documented source-system semantics without seeing PermitDiff output.
2. Reviewer B independently reviews the same material where feasible.
3. Disagreement is adjudicated and documented before benchmark execution.
4. The final label file is frozen and checksummed.

If only one qualified reviewer is available, that limitation must be disclosed and the case remains eligible only if the reasoning is explicit and reproducible. Results from singly reviewed cases should be separable from doubly reviewed cases.

### Ambiguity rule

When source semantics are genuinely ambiguous or depend on unavailable runtime state, label the case `UNKNOWN_OR_UNSUPPORTED` rather than forcing a binary security judgment.

## Systems under comparison

### PermitDiff

Run the exact frozen commit/release with:

- documented strict profile for release-gate evaluation;
- no benchmark-specific hidden configuration;
- exact command line/configuration captured in the result artifact;
- deterministic outputs retained as evidence.

### Baseline A — plain text diff

A reviewer receives a standard textual diff of baseline vs candidate plus the same source-system documentation available to other reviewers. No PermitDiff-derived annotations are shown.

This baseline represents the common minimum review mechanism, not a security analyzer.

### Baseline B — structured manual review

A reviewer receives the full baseline/candidate artifacts plus a fixed review checklist defining the same target outcome: identify material permission broadening, approval-boundary weakening, unresolved semantic uncertainty, or benign/restrictive change.

The checklist must be frozen before confirmatory execution.

### Baseline C — relevant analyzers

Include an external analyzer only when all of the following hold:

- it is publicly obtainable;
- it analyzes a genuinely overlapping permission/policy surface;
- its version and configuration can be pinned;
- its outputs can be mapped to the benchmark label without inventing semantics it does not claim.

A tool must not be included as a straw baseline merely because it produces superficially comparable output.

If no credible overlapping analyzer exists for a case family, report `not applicable` instead of forcing a comparison.

## Reviewer protocol

For human-review baselines:

- randomize case order;
- do not reveal PermitDiff output;
- use identical source documentation per case;
- record start/end time or elapsed active-review time;
- record final label and confidence;
- record whether additional documentation was consulted;
- record whether the reviewer would block, approve, or escalate the change.

If the same person performs multiple review conditions, counterbalance order where practical and disclose the carry-over risk.

## Primary metrics

The following metrics are mandatory for the confirmatory report.

### Detection metrics

For cases adjudicated as `SECURITY_RELEVANT_REGRESSION` or `BENIGN_OR_RESTRICTIVE_CHANGE`:

- true positives;
- false positives;
- true negatives;
- false negatives;
- precision;
- recall;
- specificity;
- false-positive rate;
- false-negative rate.

Do not compute precision/recall by coercing `UNKNOWN_OR_UNSUPPORTED` into either positive or negative.

### Unknown / support-boundary metrics

Report separately:

- unknown/unsupported rate;
- correct fail-closed unknown rate;
- unsupported cases incorrectly classified as safe;
- unsupported cases incorrectly classified as definite regressions when the model only justifies uncertainty;
- percentage of the corpus inside PermitDiff's documented support boundary.

### Reviewer-effort metrics

For human baselines:

- median review time per case;
- interquartile range;
- total review time;
- escalation rate;
- false-positive review burden;
- missed-regression count.

If timing conditions are too uncontrolled for inferential claims, report them descriptively rather than implying statistical significance.

### Per-category metrics

At minimum, report recall by atomic regression family where sample count is non-trivial. Small slices must show raw counts and denominators; do not publish unstable percentages without counts.

## Secondary engineering metrics

Capture, but do not confuse with detection-quality evidence:

- PermitDiff runtime;
- peak/approximate resource use when reproducible;
- deterministic-output consistency across repeated runs;
- artifact generation success;
- waiver/evidence validation behavior;
- CI integration success.

## Scoring PermitDiff outcomes

A PermitDiff result is scored from the semantic outcome, not process exit code alone.

The benchmark harness must retain enough structured output to distinguish:

- definite regression/block;
- benign/pass;
- unknown/fail-closed escalation;
- execution/configuration failure.

Execution/configuration failures are reported separately and are not silently converted into security detections.

## Error analysis

Every PermitDiff error must be classified into one of:

- implementation defect;
- unsupported semantic relation;
- adapter projection limitation;
- insufficient review corpus/scenario evidence;
- ground-truth ambiguity;
- benchmark harness defect;
- provenance/reproduction failure;
- baseline-mapping ambiguity.

The confirmatory report must preserve individual false negatives and false positives. Do not publish only aggregate metrics.

## Statistical discipline

This benchmark is primarily an engineering validation study, not a population-level clinical-style trial. Statistical methods must therefore remain proportional to sample quality.

Required discipline:

- always report raw numerators and denominators;
- report confidence intervals for key proportions when sample size makes them meaningful;
- avoid significance testing on tiny or convenience samples;
- do not infer ecosystem-wide prevalence from a curated corpus;
- distinguish historical/public cases from synthetic coverage cases;
- do not tune thresholds to maximize confirmatory metrics.

If the corpus is too small for credible inferential statistics, report descriptive evidence only.

## Reproducibility requirements

A confirmatory benchmark release must contain or reference:

- benchmark protocol version;
- frozen case manifest;
- case provenance and immutable source references;
- baseline/candidate SHA-256 digests;
- adjudicated labels and rationale;
- PermitDiff commit/release identifier;
- Python/runtime environment metadata;
- baseline-tool versions/configuration;
- exact benchmark command;
- machine-readable raw results;
- scoring script version;
- generated summary tables;
- known limitations.

The benchmark must be runnable from a clean checkout without requiring private credentials, except where an explicitly documented public-source rate limit makes an optional token useful. Vendored immutable fixtures are preferred when legally and practically appropriate.

## Data integrity

The case manifest and adjudicated label set must be checksummed before confirmatory execution.

The results artifact must record:

- protocol version;
- corpus manifest digest;
- label-set digest;
- PermitDiff commit;
- benchmark harness commit;
- timestamp;
- environment metadata.

Any change to corpus membership, labels, metric definitions, or scoring logic after freezing requires a new benchmark protocol/result version.

## Stop and restart rules

A confirmatory run must be stopped and versioned as invalidated if:

- benchmark code corrupts or drops results;
- source artifacts do not match frozen digests;
- the frozen PermitDiff version is not the one executed;
- a label file changes after execution starts;
- reviewer blinding is broken before the relevant manual-review condition completes;
- a defect makes the scoring interpretation materially wrong.

An invalidated run remains archived for auditability but is not used for product claims.

## Acceptance criteria for R3 benchmark evidence

The benchmark phase is complete only when:

1. the protocol and case schema are merged before confirmatory execution;
2. exploratory and confirmatory corpora are separated;
3. ground-truth labels are frozen independently of PermitDiff output;
4. at least text-diff and structured-manual-review baselines are executed where applicable;
5. confirmatory raw results and scoring artifacts are reproducible;
6. precision/recall/error counts and unknown/support-boundary rates are reported honestly;
7. individual false positives and false negatives are documented;
8. public/synthetic evidence is clearly separated;
9. no stronger claim is made than the measured support boundary justifies.

Meeting these criteria may justify `EXTERNALLY VALIDATED` for the benchmarked scope. It does not imply `PILOT VALIDATED`, `PRODUCTION VALIDATED`, or `COMMERCIAL VALIDATED`.

## Versioning

Initial protocol version: `r3-benchmark-protocol-v1`.

Changes before the first confirmatory freeze may be made through normal reviewed pull requests. Once a confirmatory corpus is frozen against this protocol, substantive changes to labels, metrics, baselines, or scoring rules require `v2` or a later protocol version.

## Immediate implementation sequence

After this protocol is merged:

1. define the machine-readable case-manifest schema;
2. assemble an exploratory corpus first;
3. implement provenance and digest validation;
4. implement text-diff and PermitDiff benchmark runners;
5. define/freeze the manual-review checklist;
6. run exploratory evaluation and fix protocol/harness defects;
7. create and checksum the confirmatory corpus and label set;
8. execute the frozen confirmatory benchmark;
9. publish raw results, summary metrics, limitations, and claim updates.
