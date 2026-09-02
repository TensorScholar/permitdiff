# Limitations

PermitDiff optimizes for credible, bounded release evidence. It intentionally does not claim complete authorization verification.

## Corpus completeness

Only supplied scenarios are evaluated dynamically. A missing scenario can hide an effective permission change. Use production-derived traces after redaction, boundary cases, abuse cases, incident reproductions, and explicit ownership to improve corpus quality.

PermitDiff also performs bounded static authority analysis over policy changes, but that is not a proof that the scenario corpus is exhaustive.

## Static-analysis boundary

The built-in analyzer proves only a limited set of monotone containment relationships for the native policy language. It handles selected finite/glob domains, optional boolean constraints, numeric bounds, finite-set predicates, rule addition/removal, default relaxation, and some precedence changes.

It does not provide general glob-language containment, SMT solving, arbitrary predicate equivalence, or complete reachability analysis. When a changed construct falls outside the bounded model, PermitDiff reports `unknown`; an unwaived `unknown` fails closed.

A `potential_expansion` is conservative policy-level evidence that authority can widen. It is not a claim that every request in the widened region is reachable in a deployed system with external identity, tool, network, or business constraints.

## Policy-language scope

The built-in language is deterministic and intentionally small. It does not model external state, relationship-based access control, distributed identity, time windows, quotas, arbitrary functions, runtime credential possession, or side effects outside the normalized action model. Normalize those systems into stable scenarios or build a narrow adapter that preserves their semantics.

## Annotation trust

`security_metadata_trusted` records a corpus/policy assertion; PermitDiff does not attest the tool server. Establish trust through deployment identity, signed metadata, allowlisted registries, or another control outside this tool.

## Waiver scope

Observed-transition waivers bind to an exact scenario transition and action fingerprint. Static-authority waivers additionally bind to the exact finding plus baseline and candidate policy digests. They are release-review evidence, not runtime authorization.

A waiver can still encode a bad human decision. Expiry, exact matching, digest binding, and unused-waiver checks reduce replay and staleness risk; they do not replace accountable review.

## No runtime enforcement

A passing gate cannot force a deployed agent to use the reviewed policy, cannot prevent tool-call bypasses, cannot prove credentials are correctly bound to actions, and cannot validate approval execution. Those are runtime authorization and execution-integrity responsibilities outside PermitDiff.

## Severity is advisory

Scenario risk and transition severity improve review prioritization. They are not a quantitative risk model and should not replace organizational threat analysis.

## Alpha compatibility

The `permitdiff.dev/v1alpha1` policy/gate contracts and `v1alpha1` report schemas may change before v1. Pin PermitDiff versions in CI and review the changelog before upgrading.
