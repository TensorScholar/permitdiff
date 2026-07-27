# Release readiness

A release is publishable only when all checks below are evidenced—not merely configured.

- CI passes on Python 3.11–3.14.
- Ruff, strict mypy, schema drift, tests, and clean-wheel smoke tests pass.
- Dependency audit, CodeQL, and OpenSSF Scorecard have no unresolved release blockers.
- Tag, package version, changelog, and citation metadata match.
- Wheel and sdist pass metadata validation.
- CycloneDX SBOM, SHA-256 checksums, and GitHub provenance/SBOM attestations exist.
- The release candidate has run successfully in at least one external repository.
- A rollback path is documented: remove the affected release, yank the PyPI version, and publish a corrected version—never replace artifacts in place.

`0.1.0rc1` is a production-grade release candidate, not a universal production-fitness claim.
