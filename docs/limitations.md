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

## Claude Code native preapproval projection

The development-line Claude Code adapter is intentionally narrower than a full settings importer. It accepts only explicit `permissions.defaultMode = "dontAsk"` pairs with unchanged `permissions.deny` and `permissions.ask`, then projects a documented subset of `permissions.allow` into PermitDiff policies.

Bare-tool translation is limited to `Bash`, `PowerShell`, `WebFetch`, and `WebSearch`. Other bare tools remain opaque because Claude Code tool classes have materially different approval behavior; if an opaque allow rule changes, the adapter fails closed rather than inferring equivalence. Exact `WebFetch(domain:HOST)` rules are also projected as WebFetch preapprovals. Same-effect scoped Bash/PowerShell rules may be removed as semantic noise only when documented broader semantics subsume them.

Non-`permissions` root settings are not evaluated. Their values are reduced to canonical SHA-256 digests for equality checks, so semantically identical JSON with different key ordering does not create drift and raw ignored values are not copied into evidence. Evidence records only root-key names and which ignored keys differ. If any ignored root key changes, the adapter fails until the reviewer explicitly passes `--allow-ignored-root-changes`. This is an acknowledgement of projection scope, not approval of the ignored change.

Claude Code's current permission documentation states that domain-scoped WebFetch rules can also modify sandbox network-domain policy. PermitDiff models exact `WebFetch(domain:HOST)` rules in this adapter only as WebFetch preapprovals. Any exact WebFetch-domain declaration change requires `--acknowledge-webfetch-sandbox-gap`, even when the declaration is redundant for preapproval because bare `WebFetch` already exists. That acknowledgement permits analysis of the preapproval projection only; it is not evidence that the sandbox/network consequence was reviewed, accepted, or waived.

`WebFetch(domain:*)` is not treated as semantically identical to bare `WebFetch`: both can preapprove all WebFetch calls, but their sandbox behavior differs. A changed wildcard-domain rule is unsupported and causes the adapter to fail closed.

The normalization evidence records declared exact WebFetch domains, `ignored_root_changes_acknowledged`, and `webfetch_sandbox_gap_acknowledged` so downstream reviewers can distinguish a projection with known omitted surfaces. These fields record explicit awareness only; they are not risk-acceptance decisions.

The reserved `_claude.permission_domain` field used in review scenarios is normalization metadata. It is not asserted to be the raw Claude Code WebFetch input schema.

## Annotation trust

`security_metadata_trusted` records a corpus/policy assertion; PermitDiff does not attest the tool server. Establish trust through deployment identity, signed metadata, allowlisted registries, or another control outside this tool.

## Waiver scope

Observed-transition waivers bind to an exact scenario transition and action fingerprint. Static-authority waivers additionally bind to the exact finding plus baseline and candidate policy digests. They are release-review evidence, not runtime authorization.

A waiver can still encode a bad human decision. Expiry, exact matching, digest binding, and unused-waiver checks reduce replay and staleness risk; they do not replace accountable review.

For native adapters, a waiver applies only to the normalized PermitDiff finding. It does not waive omitted semantics in the source system. In particular, a Claude WebFetch preapproval waiver does not waive sandbox-network behavior, and a PermitDiff result does not waive non-permission root-key changes surfaced only as adapter evidence. Projection acknowledgement flags are likewise not waivers.

## No runtime enforcement

A passing gate cannot force a deployed agent to use the reviewed policy, cannot prevent tool-call bypasses, cannot prove credentials are correctly bound to actions, and cannot validate approval execution. Those are runtime authorization and execution-integrity responsibilities outside PermitDiff.

## Severity is advisory

Scenario risk and transition severity improve review prioritization. They are not a quantitative risk model and should not replace organizational threat analysis.

## Alpha compatibility

The `permitdiff.dev/v1alpha1` policy/gate contracts and `v1alpha1` report schemas may change before v1. Pin PermitDiff versions in CI and review the changelog before upgrading.
