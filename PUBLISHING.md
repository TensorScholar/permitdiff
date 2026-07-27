# Publishing

PermitDiff is published only from GitHub Actions.

1. Confirm every required check on `main` is green.
2. Run the release candidate in at least one external repository.
3. Update `_version.py`, `CHANGELOG.md`, and `CITATION.cff` together.
4. Create a signed matching tag, for example:

   ```bash
   git tag -s v0.1.0rc1 -m "PermitDiff v0.1.0rc1"
   git push origin v0.1.0rc1
   ```

5. The release workflow validates tag/version alignment, builds once, smoke-tests the wheel, emits a CycloneDX SBOM and SHA-256 checksums, generates GitHub provenance/SBOM attestations, creates the GitHub release, then publishes through the protected `pypi` environment using Trusted Publishing.

Never publish from a workstation or store a long-lived PyPI token in repository secrets.
