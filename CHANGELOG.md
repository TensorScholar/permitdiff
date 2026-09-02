# Changelog

All notable changes are documented here. Semantic Versioning begins when the `v1` schema stabilizes.

## Unreleased

### Added

- bounded static authority analysis for policy-level scope widening, constraint weakening, deny narrowing, default relaxation, and precedence uncertainty;
- separate static-authority findings in comparison, Markdown, console, JSON schema, and SARIF outputs;
- exact expiring authority waivers bound to finding fingerprints and baseline/candidate policy digests;
- a reproducible public historical Claude Code permission-widening validation pilot with frozen source blobs, semantic de-noising, negative controls, and an executable regression contract;
- a read-only external-repository execution workflow that builds and installs the wheel under test, verifies pinned external source commits/blobs, executes PermitDiff from the external repository root, and publishes machine-readable evidence.

### Changed

- release evidence now distinguishes observed scenario transitions from conservative policy-level authority findings;
- strict gates fail closed on unsupported or ambiguous static containment unless the exact finding is explicitly waived;
- canonical input validation now rejects non-serializable JSON values in action arguments and dynamic action context before evidence hashing.

## [0.1.0rc1] - 2026-07-27

### Added

- deterministic permission comparison over a bounded scenario corpus;
- privilege-expansion, approval-bypass, structural-diff, and rule-coverage analysis;
- exact expiring waivers and configurable release gates;
- console, JSON, Markdown, and SARIF 2.1.0 outputs;
- CLI, Python API, starter project, and composite GitHub Action;
- strict trust handling for MCP-style annotations;
- CodeQL, OpenSSF Scorecard, SBOM, Trusted Publishing, and build provenance workflows;
- concise visual README, citation metadata, and commercial adoption path.
