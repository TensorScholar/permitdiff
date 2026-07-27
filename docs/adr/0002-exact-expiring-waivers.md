# ADR 0002: Waivers are exact and expiring

- Status: Accepted
- Date: 2026-07-27

## Context

Release gates need controlled exceptions, but broad suppressions become permanent authorization debt.

## Decision

Bind each waiver to one scenario ID and exact baseline/candidate effects. Require a substantive reason and expiry date. Never support wildcard waivers.

## Consequences

Approved expansions remain visible and auditable. Policy evolution invalidates stale waivers automatically, at the cost of deliberate maintenance.
