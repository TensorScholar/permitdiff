# Security policy

## Supported versions

| Version | Security fixes |
|---|---|
| `0.1.0rc1` | Yes |
| Older snapshots | No |

## Report privately

Do not disclose suspected vulnerabilities in a public issue. Use GitHub private vulnerability reporting for `TensorScholar/permitdiff` and include the affected version, reproduction, impact, and proposed mitigation when available.

A complete report will be acknowledged within five business days. Disclosure is coordinated after a fix or effective mitigation is available.

## Security boundary

PermitDiff is deterministic release analysis—not a runtime authorization boundary. A passing gate does not validate identity, authentication, sandboxing, tool-server honesty, corpus completeness, CI-runner integrity, or deployment configuration. See the [threat model](docs/threat-model.md) and [limitations](docs/limitations.md).

## Release integrity

Official releases are built from tags through GitHub Actions, published with PyPI Trusted Publishing, accompanied by checksums and a CycloneDX SBOM, and linked to GitHub build-provenance attestations. Consumers should pin versions and verify provenance before sensitive use.
