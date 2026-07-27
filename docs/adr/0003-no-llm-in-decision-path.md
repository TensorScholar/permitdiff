# ADR 0003: No LLM in the comparison or gate path

- Status: Accepted
- Date: 2026-07-27

## Context

A model-based judge could offer flexible policy interpretation but would introduce nondeterminism, external data transfer, cost, latency, and circular trust into a security release gate.

## Decision

The core comparison, severity classification, waiver binding, and gate verdict are fully deterministic and offline.

## Consequences

PermitDiff can be reproduced and audited. Teams may use external models to propose scenarios or explanations, but generated artifacts must enter through the same validated corpus and human review process.
