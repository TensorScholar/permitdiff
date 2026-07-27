# Limitations

PermitDiff optimizes for credible, bounded release evidence. It intentionally does not claim complete authorization verification.

## Corpus completeness

Only supplied scenarios are evaluated. A missing scenario can hide an effective permission change. Use production-derived traces after redaction, boundary cases, abuse cases, incident reproductions, and explicit ownership to improve corpus quality.

## Policy-language scope

The built-in language is deterministic and intentionally small. It does not model external state, relationship-based access control, distributed identity, time windows, quotas, or arbitrary functions. Normalize those systems into stable scenarios or build an adapter that preserves their semantics.

## Annotation trust

`security_metadata_trusted` records a corpus/policy assertion; PermitDiff does not attest the tool server. Establish trust through deployment identity, signed metadata, allowlisted registries, or another control outside this tool.

## No runtime enforcement

A passing gate cannot force a deployed agent to use the reviewed policy, cannot prevent tool-call bypasses, and cannot validate approval execution. Runtime authorization and observability remain required.

## Severity is advisory

Scenario risk and transition severity improve review prioritization. They are not a quantitative risk model and should not replace organizational threat analysis.

## Alpha compatibility

The `permitdiff.dev/v1alpha1` schema may change before v1. Pin PermitDiff versions in CI and review the changelog before upgrading.
