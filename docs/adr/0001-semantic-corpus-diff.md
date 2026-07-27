# ADR 0001: Compare effective permissions over an explicit corpus

- Status: Accepted
- Date: 2026-07-27

## Context

Raw YAML diffs cannot reliably communicate the consequence of ordered policy rules. Full symbolic equivalence would require a substantially more restrictive language and solver complexity.

## Decision

Evaluate the same explicit scenario corpus against baseline and candidate policies, then classify effect transitions and observed rule coverage.

## Consequences

The result is deterministic, understandable, and CI-friendly. Completeness depends on corpus quality and must never be presented as formal verification.
