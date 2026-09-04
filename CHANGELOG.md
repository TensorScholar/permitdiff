# Changelog

All notable changes are documented here. Semantic Versioning begins when the `v1` schema stabilizes.

## [Unreleased]

### Added

- added a bounded Claude Code native preapproval adapter and `permitdiff claude compare` command for explicit `dontAsk` project settings, with source digests, translated/opaque/redundant-rule evidence, ignored root-key drift, normal PermitDiff reports, and optional release gates;
- added explicit projection acknowledgements for changed non-`permissions` root settings and changed exact WebFetch-domain rules; both acknowledgements are recorded in adapter evidence and authorize analysis of the bounded projection only;
- added executable regression coverage that reproduces the public historical Claude permission pilot directly from its frozen native settings snapshots while preserving the pilot's narrower preapproval-projection claim;
- added provenance-bound Git baseline resolution for `permitdiff compare --baseline-ref`, including exact commit/blob identity, raw SHA-256 evidence, traversal-safe repository-relative paths, and no baseline checkout;
- added Composite Action baseline provenance outputs (`baseline_commit`, `baseline_object`, `baseline_evidence`) and reviewer-visible Git source identity in the Actions step summary.

### Changed

- advanced mutable source to `0.1.0rc3.dev0` after the `0.1.0rc2` release attempt so post-release development cannot rebuild different source under an already published version identity;
- separated CI development-metadata validation from immutable publish-time tag/changelog/citation validation while keeping `CITATION.cff` bound to the latest actual release;
- configured future alpha, beta, and release-candidate tags to create GitHub Releases with explicit prerelease metadata;
- clarified native-adapter governance: omitted source surfaces must be visible in evidence, known projection gaps require explicit acknowledgement before analysis, waivers apply only to normalized findings, and bounded projections must not be described as full effective-authority proofs;
- changed the example permission scan into an end-to-end Composite Action contract that resolves a Git baseline, asserts the intentional BLOCK, verifies provenance outputs, and uploads the Action-generated SARIF;
- extended the isolated installed-wheel smoke test to exercise normalized policies, provenance-bound Git baselines, and the native Claude preapproval projection so release-facing interfaces are proven from the built distribution rather than only editable source installs;
- changed tagged publication into a draft-first transaction: verified release assets are attached to an unpublished GitHub Release, PyPI publishes next, and the GitHub Release becomes public only after PyPI succeeds.

### Fixed

- bound observed-transition waivers to exact baseline/candidate policy digests so a reviewed scenario approval cannot replay after either policy drifts; waivers without digests now fail validation instead of matching silently;
- stopped treating `WebFetch(domain:*)` as semantically identical to bare `WebFetch`; current Claude Code behavior gives the domain form additional sandbox-network effects, so changed wildcard-domain rules now fail closed instead of being collapsed;
- prevented silent PASS interpretation when Claude settings change outside the modeled projection: ignored root drift and exact WebFetch-domain changes now fail until their distinct projection gaps are explicitly acknowledged;
- qualified the public Claude validation evidence as two modeled `permissions.allow` preapproval expansions and explicitly preserved the concurrent `enabledPlugins` change as out-of-projection evidence;
- made the Composite Action fail if Markdown and SARIF renderers disagree on exit semantics or if a valid comparison fails to produce both required review artifacts;
- replaced the generated starter's unavailable PyPI install with the actual `v0.1.0rc2` GitHub Release wheel pinned by its published SHA-256, so first-run CI remains reproducible while PyPI Trusted Publishing is not yet configured.

## [0.1.0rc2] - 2026-09-02

### Fixed

- preserved reproducible CycloneDX generation while adding a deterministic `urn:uuid:` `serialNumber` derived from canonical BOM content and the release-wheel SHA-256, making the SBOM recognizable to GitHub artifact attestation without reintroducing random or timestamp entropy;
- added a regression contract for deterministic SBOM identity and release-workflow finalization;
- preserved `v0.1.0rc1` as an immutable failed release-attempt tag after its workflow stopped at SBOM attestation before artifact upload, GitHub Release creation, or PyPI publication.

## [0.1.0rc1] - 2026-09-02

### Added

- deterministic permission comparison over a bounded scenario corpus;
- privilege-expansion, approval-bypass, structural-diff, and rule-coverage analysis;
- bounded static authority analysis for policy-level scope widening, constraint weakening, deny narrowing, default relaxation, and precedence uncertainty;
- separate static-authority findings in comparison, Markdown, console, JSON schema, and SARIF outputs;
- exact expiring scenario and authority waivers, with authority waivers bound to finding fingerprints and baseline/candidate policy digests;
- configurable release gates, console/JSON/Markdown/SARIF 2.1.0 outputs, CLI, Python API, starter project, and composite GitHub Action;
- strict trust handling for MCP-style annotations;
- a reproducible public historical Claude Code permission-widening validation pilot with frozen source blobs, semantic de-noising, negative controls, and an executable regression contract;
- a read-only external-repository execution workflow that builds and installs the wheel under test, verifies pinned external source commits/blobs, executes PermitDiff from that repository root, and publishes machine-readable evidence;
- CodeQL, OpenSSF Scorecard, SBOM, Trusted Publishing, checksums, and build-provenance release workflows;
- concise visual README, citation metadata, responsible disclosure guidance, and commercial adoption path.

### Changed

- release evidence distinguishes observed scenario transitions from conservative policy-level authority findings;
- strict gates fail closed on unsupported or ambiguous static containment unless the exact finding is explicitly waived;
- canonical input validation rejects non-serializable JSON values in action arguments and dynamic action context before evidence hashing.
