# R3 strategic-review response

## Decision

The 2026-09-12 one-shot senior strategic/research review is accepted as a material methodology input, not as implementation certification.

The project retains the core product thesis but narrows the research thesis to an empirical question:

> Within a documented native permission projection, does separating witnessed authorization changes, bounded potential widening, and semantic uncertainty improve the detection-effort trade-off of authorization-change review over structured manual review and simpler automated checks on previously unseen configuration changes?

Research novelty remains **unestablished** until external evidence supports a result that simpler techniques do not explain or match.

## Accepted corrections

The following review findings are adopted before canonical labels or product execution:

1. Ground truth must separate source semantic relation from tool support, organizational intent, and source-semantic resolvability.
2. Tool abstention / unsupported behavior must not redefine known source-level positives or disappear from their denominator.
3. Scenario construction requires explicit provenance; answer-informed diagnostic scenarios cannot be represented as ordinary pre-existing evidence.
4. Human ground-truth adjudicators cannot be reused as uncontaminated timed baseline reviewers for the same cases in confirmatory evaluation.
5. A pre-execution digest lock prevents mutation but does not erase prior human/developer exposure; inspected cases are not fresh holdout evidence later.
6. Historical source artifacts will be evaluated under a frozen semantic replay contract unless contemporaneous semantics can be reconstructed reliably under a separately preregistered policy.
7. The primary product-value comparison should be PermitDiff-assisted review versus structured manual review; a simple native checker and analysis-channel ablations should be included where semantically honest.

These decisions are formalized by `docs/r3-measurement-contract-amendment.md` and the machine-readable `validation/r3-benchmark/exploratory/measurement-contract-v2.json`.

## Findings accepted as strategic guidance, not immediate implementation requirements

- Deeper precedence/reachability analysis is conditional. It moves forward before confirmation only if an existing in-scope claim is invalid without it or exploratory evidence shows it is a dominant failure mode.
- Adapter breadth remains deferred until single-adapter evidence exists.
- Bounded prospective user/problem discovery is allowed before benchmark completion, but customer-specific engineering and pilot-driven scope expansion remain deferred.
- Evidence/provenance machinery is support infrastructure unless independently shown to contribute a research result.

## Important qualification

Established systems such as access-control policy analyzers, native cloud authorization analyzers, policy testing systems, and provenance frameworks constrain novelty claims. They are not automatically executable benchmark baselines. An external analyzer is included in quantitative comparison only when its semantics overlap faithfully enough to avoid a straw translation.

## Immediate consequence for draft PR #50

PR #50 remains a draft.

The pre-review staging review-packet and adjudication tooling still encodes the older conflated three-way ground-truth label. It is therefore **superseded for canonical adjudication** and must not be used to lock exploratory labels until it is revised to implement the new measurement contract and exact-head executable validation passes.

Discovery observability, public-only retrieval, screening, deterministic selection, and materialization mechanics are not invalidated by this amendment because the review did not change their frozen outcome-blind membership rules.

## Maturity consequence

No maturity upgrade follows from this review or amendment.

- verified core remains `ENGINEERING VERIFIED` within its documented boundary;
- PR #50 staging work remains unverified until exact-head executable checks pass;
- R3 remains pre-execution;
- `EXTERNALLY VALIDATED` remains unsupported.
