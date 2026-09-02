# Release readiness

A release is publishable only when all checks below are evidenced—not merely configured.

- CI passes on Python 3.11–3.14.
- Ruff, strict mypy, schema drift, tests, and clean-wheel smoke tests pass.
- Dependency audit, CodeQL, and OpenSSF Scorecard have no unresolved release blockers.
- The canonical release tag, package version, changelog entry, and citation metadata match exactly.
- The release metadata contract is rehearsed in ordinary CI before any tag is created.
- Wheel and sdist pass metadata validation.
- CycloneDX SBOM, SHA-256 checksums, and GitHub provenance/SBOM attestations exist. The CycloneDX document is generated reproducibly and finalized with a deterministic `urn:uuid:` `serialNumber` bound to canonical BOM content and the release-wheel SHA-256 before attestation.
- The release candidate has run successfully in at least one external repository. The canonical pre-release evidence is `.github/workflows/external-validation.yml`: it builds and installs the wheel under test, checks out a pinned independently maintained public repository read-only, verifies the external commit and source blobs, executes PermitDiff from that repository root, and uploads machine-readable evidence.
- The tagged release re-runs the same bounded external-repository validation against the exact release wheel. `external-repository-evidence.json` is checksummed, attested, retained in the release artifact bundle, and attached to the GitHub Release alongside the wheel, sdist, SBOM, and `SHA256SUMS`.
- PyPI receives only the wheel and sdist from an explicit allowlisted staging directory; release evidence, checksums, and SBOM files are never passed to the package publisher.
- A rollback path is documented: remove the affected GitHub Release if necessary, yank the PyPI version, and publish a corrected version—never replace immutable release artifacts in place.

External-repository execution demonstrates packaging and semantic-analysis compatibility in a real external project checkout. It is not evidence of third-party adoption, endorsement, or universal compatibility.

`v0.1.0rc1` is retained as an immutable failed release-attempt tag: its workflow stopped at SBOM attestation before distribution upload, GitHub Release creation, or PyPI publication. `0.1.0rc2` is the corrected production-grade release candidate, not a universal production-fitness claim.
