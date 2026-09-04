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
- PyPI publishing identity is verified **before a release tag is created**. The Trusted Publisher must match repository owner `TensorScholar`, repository `permitdiff`, workflow `release.yml`, and GitHub environment `pypi`; the publish job keeps `id-token: write` scoped to that job. If the PyPI project does not yet exist, a matching pending Trusted Publisher must be configured before tagging. A pending publisher is an authorization path for first publication, not a reservation of the project name.
- PyPI receives only the wheel and sdist from an explicit allowlisted staging directory; release evidence, checksums, and SBOM files are never passed to the package publisher.
- GitHub Release creation and PyPI publication are treated as a distributed transaction with no atomic commit across services. After build, validation, checksums, and attestations succeed, the workflow creates an **unpublished draft GitHub Release** and attaches the verified assets. PyPI publication runs only after that draft exists. The draft is published only after PyPI succeeds. This keeps the GitHub publication stage reversible until the less-reversible package-index publication has committed, while retaining the tag as the immutable workflow source identity.
- A partial release is not repaired by rebuilding or replacing artifacts under the same version. If PyPI fails, keep the GitHub Release unpublished, repair the external publishing dependency, and rerun the failed publication path against the retained immutable distributions. If PyPI succeeds but final GitHub Release publication fails, rerun only the release-finalization stage. If the exact artifacts are no longer recoverable, advance the version rather than recreate them.
- A rollback path is documented: remove an unpublished draft when appropriate; for already published artifacts, yank the affected PyPI version or remove the affected GitHub Release only as an incident response, then publish a corrected version—never replace immutable release artifacts in place.

External-repository execution demonstrates packaging and semantic-analysis compatibility in a real external project checkout. It is not evidence of third-party adoption, endorsement, or universal compatibility.

`v0.1.0rc1` is retained as an immutable failed release-attempt tag: its workflow stopped at SBOM attestation before distribution upload, GitHub Release creation, or PyPI publication. `v0.1.0rc2` corrected that SBOM failure and completed the build, external validation, attestations, artifact upload, and GitHub Release stages, but its PyPI publication remains incomplete because the matching Trusted Publisher was not configured. Issue #33 is the release blocker and recovery record. Neither release-candidate history is a universal production-fitness claim.
