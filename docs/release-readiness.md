# Release readiness

A release is publishable only when all checks below are evidenced—not merely configured.

- CI passes on Python 3.11–3.14.
- Ruff, strict mypy, schema drift, tests, and clean-wheel smoke tests pass.
- Dependency audit, CodeQL, and OpenSSF Scorecard have no unresolved release blockers.
- Tag, package version, changelog, and citation metadata match.
- Wheel and sdist pass metadata validation.
- CycloneDX SBOM, SHA-256 checksums, and GitHub provenance/SBOM attestations exist.
- The release candidate has run successfully in at least one external repository. The canonical pre-release evidence is `.github/workflows/external-validation.yml`: it builds and installs the wheel under test, checks out a pinned independently maintained public repository read-only, verifies the external commit and source blobs, executes PermitDiff from that repository root, and uploads machine-readable evidence.
- A rollback path is documented: remove the affected release, yank the PyPI version, and publish a corrected version—never replace artifacts in place.

External-repository execution demonstrates packaging and semantic-analysis compatibility in a real external project checkout. It is not evidence of third-party adoption, endorsement, or universal compatibility.

`0.1.0rc1` is a production-grade release candidate, not a universal production-fitness claim.
