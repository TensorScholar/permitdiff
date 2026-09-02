# ADR 0002: Waivers are exact and expiring

- Status: Accepted
- Date: 2026-07-27

## Context

Release gates need controlled exceptions, but broad suppressions become permanent authorization debt. PermitDiff has two distinct evidence channels: observed scenario transitions and bounded static authority findings. An exception for one channel must never implicitly suppress the other.

## Decision

Use separate, exact waiver types for each evidence channel. Never support wildcard waivers.

Observed-transition waivers bind to one scenario ID, exact baseline/candidate effects, and the normalized action fingerprint.

Static-authority waivers bind to one finding kind and finding fingerprint **and** to the exact baseline and candidate policy digests. This prevents a policy-level approval from replaying after either compared policy changes, even if a syntactically similar finding would otherwise receive the same fingerprint.

Every waiver requires a substantive reason and expiry date. An issue URL is optional. Active waivers that no longer match gate-relevant evidence can be rejected with `fail_on_unused_waivers`.

## Consequences

Approved expansions remain visible and auditable. A transition waiver cannot waive a policy-level authority finding, and a static-authority waiver cannot waive an observed scenario transition. Policy or action drift invalidates stale approvals automatically, at the cost of deliberate maintenance.
