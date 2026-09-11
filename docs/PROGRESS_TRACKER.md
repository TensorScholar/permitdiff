# PermitDiff Progress Tracker

## Project Phase

R2 complete — strict-profile integrity and evidence-boundary hardening are merged and engineering verified.

Current focus: R3 external-validation breadth and benchmark protocol.

## Main SHA

`5fa1ed949a71637d6a25466d80d84d62e87a9e4e`

## Current Branch

`docs/add-progress-tracker`

## Current PR

`#41` — Add canonical progress tracker.

## Engineering Maturity

ENGINEERING VERIFIED for the implemented deterministic comparison path, bounded static authority analysis, fail-closed static unknown handling, waiver digest binding, differential evidence integrity, claim-boundary reporting, strict-profile invariants, security-relevant scalar type integrity, Claude projection-gap evidence binding, packaging, external-repository integration validation, and the current release pipeline controls covered by repository tests and CI.

This does not elevate unsupported global, runtime, production, or commercial authorization claims.

## Product Readiness

IMPLEMENTED / ENGINEERING VERIFIED for the current core release-time authorization-regression workflow.

The product is not yet EXTERNALLY VALIDATED, PILOT VALIDATED, PRODUCTION VALIDATED, or COMMERCIAL VALIDATED.

## External Validation

Limited reproducible integration validation exists, including the pinned external-repository validation workflow. This demonstrates compatibility against a real external repository, but it is not independent benchmark validation and does not establish detection quality across broader policy ecosystems.

Independent benchmark validation remains pending.

## Commercial Validation

Not validated. No paying customers, enterprise pilots, or production deployments are claimed.

## Completed Milestones

- Deterministic semantic permission comparison.
- Bounded static declared-authority analysis with fail-closed unknowns.
- Candidate rule coverage gate.
- Transition waiver digest binding.
- Differential evidence integrity gate.
- Claim-boundary hardening in human and machine reports.
- Explicit fail-closed strict profile with pinned security-relevant settings.
- Strict security-relevant boolean and integer validation at external input boundaries.
- Claude native projection-gap acknowledgements bound to durable evidence output when active.
- Release hardening, provenance, SBOM, and attestation controls.
- Trusted Apple Silicon self-hosted CI path for required checks while GitHub-hosted Actions quota is unavailable.
- Fork-safety guard preventing untrusted fork PR code from executing on the persistent personal runner.
- Exact-head R2 verification across Python 3.11, 3.12, 3.13, and 3.14 plus quality, packaging, security, example-scan, and external-repository checks.

## Active Work

- Land this canonical tracker with the post-R2 state.
- Define the R3 external benchmark protocol before collecting broad evidence.
- Expand representative validation cases without widening product scope prematurely.

## Remaining Checklist

- [x] R2 strict profile integrity.
- [x] Validate strict-profile configuration invariants against the actual schema and CLI model.
- [x] Harden security-relevant scalar input boundaries against coercive type confusion.
- [x] Bind active Claude projection-gap acknowledgements to durable evidence.
- [x] Restore executable required CI through the trusted self-hosted runner path.
- [ ] Merge the canonical progress tracker.
- [ ] Freeze an R3 benchmark protocol with explicit hypotheses, frozen corpus, baselines, and adjudication rules.
- [ ] Expand external validation corpus across representative supported policy/adaptor cases.
- [ ] Benchmark detection quality against text diff, manual review, and relevant analyzers.
- [ ] Measure precision, recall, false-positive burden, reviewer time, and unsupported/unknown coverage.
- [ ] Separate exploratory benchmark work from confirmatory evidence before making stronger external claims.

## Blockers

No current engineering blocker.

GitHub-hosted Actions quota remains an external account constraint. Required PR validation is operational on the trusted self-hosted runner, so this is not currently blocking engineering verification.

## Risks

- Bounded analysis does not compute exhaustive global effective authority.
- Scenario evidence is limited to supplied review cases.
- Native adapters can only make claims within their documented projection boundaries.
- Persistent self-hosted runners are a trust boundary and must not execute untrusted fork PR code.
- The private/free security path uses `pip-audit` plus security-focused Ruff rules; this is narrower than CodeQL and must not be represented as equivalent coverage.
- External benchmark breadth is limited.
- Commercial demand is unproven.

## Supported Claims

- Deterministic semantic comparison of supported PermitDiff policy semantics.
- Observed corpus transition evidence for supplied scenarios.
- Bounded static declared-authority over-approximation with fail-closed unknowns.
- Deterministic CI gating with exact, digest-bound waivers.
- Differential evidence requirements when enabled by the gate profile.
- Explicit fail-closed strict-profile invariants for the implemented release gate.
- Type-exact validation for security-relevant gate and trust/annotation scalar fields covered by the current model.
- Durable Claude adapter evidence is required when supported projection-gap acknowledgements are actively exercised.

## Unsupported Claims

- Exhaustive authorization safety proof.
- Complete global reachability or effective-authority analysis.
- Perfect semantic equivalence across arbitrary authorization systems.
- Runtime authorization safety guarantee.
- Production security guarantee.
- Independent external benchmark validation.
- Production, enterprise, or commercial adoption.

## Latest Tests

PR #42 head `353e87f0afc3b78bab6c4015379d7d62d6f18a34` completed executable exact-head verification successfully before merge.

Verified jobs included:

- Python 3.11 pytest.
- Python 3.12 pytest.
- Python 3.13 pytest.
- Python 3.14 pytest.
- Quality checks: release-lifecycle validation, Ruff formatting/lint, mypy, generated-schema verification, and intentional policy-block verification.
- Package build, Twine validation, and installed-wheel smoke test.
- Dependency audit.
- Security-focused static analysis.
- Example permission scan.
- External repository validation.

PR #42 then merged to `main` as `5fa1ed949a71637d6a25466d80d84d62e87a9e4e`.

## Latest CI

PR #43 established and exact-head verified the trusted self-hosted CI architecture, then merged to `main` as `a76e47c99b5ddac27e00e525e7cf99035f7e0c61`.

PR #42 subsequently passed all four required workflows on its exact head using that CI path:

- CI.
- Security.
- External repository validation.
- Example permission scan.

Historical workflow runs that failed before job execution because of GitHub-hosted Actions quota are not treated as code regressions.

## Local/GitHub Sync Status

User-local checkout state is UNKNOWN unless explicitly inspected.

Remote canonical `main` is verified at `5fa1ed949a71637d6a25466d80d84d62e87a9e4e` after PR #42 merged.

## Next Critical Action

Merge this tracker after its documentation-only exact-head checks complete, then freeze the R3 benchmark protocol before broadening external evidence collection.

## Important Decisions

- Keep PermitDiff as a modular monolith and release-time authorization regression assurance layer.
- Preserve the distinction between observed corpus evidence and bounded static authority findings.
- Do not describe bounded analysis as exhaustive effective-authority proof.
- Do not add runtime authorization, dashboards, distributed infrastructure, or formal solvers without evidence that they are required.
- Treat `--strict` as an internal CLI profile that is mutually exclusive with custom `--gate`; do not conflate it with a gate-file field unless the schema intentionally changes later.
- Keep self-hosted CI restricted to trusted same-repository code; fork-authored PR jobs must not execute on the persistent personal Mac runner.
- Do not equate the current private/free static-security path with CodeQL coverage.
- Do not upgrade maturity beyond ENGINEERING VERIFIED until independent external evidence justifies it.
