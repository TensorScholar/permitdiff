from __future__ import annotations

import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from scripts.check_release import validate_release_metadata
from scripts.finalize_cyclonedx_sbom import finalize_cyclonedx_sbom

from permitdiff import __version__

ROOT = Path(__file__).resolve().parents[1]
_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")


def _write_metadata(root: Path, *, changelog: str, citation_date: str) -> None:
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "CITATION.cff").write_text(
        "\n".join(
            [
                "cff-version: 1.2.0",
                'title: "PermitDiff"',
                f"version: {__version__}",
                f"date-released: {citation_date}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_release_metadata_uses_one_version() -> None:
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert citation["version"] == __version__
    assert f"## [{__version__}]" in changelog


def test_current_release_metadata_is_coherent() -> None:
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    release_date = validate_release_metadata(f"v{__version__}", ROOT)

    assert release_date.isoformat() == str(citation["date-released"])


def test_release_metadata_rejects_noncanonical_tag() -> None:
    with pytest.raises(ValueError, match="expected release tag"):
        validate_release_metadata(__version__, ROOT)


def test_release_metadata_rejects_duplicate_changelog_entries(tmp_path: Path) -> None:
    changelog = "\n".join(
        [
            "# Changelog",
            "",
            f"## [{__version__}] - 2026-09-02",
            "",
            "- first",
            "",
            f"## [{__version__}] - 2026-09-02",
            "",
            "- duplicate",
            "",
        ]
    )
    _write_metadata(tmp_path, changelog=changelog, citation_date="2026-09-02")

    with pytest.raises(ValueError, match="exactly one dated entry"):
        validate_release_metadata(f"v{__version__}", tmp_path)


def test_release_metadata_rejects_citation_date_drift(tmp_path: Path) -> None:
    changelog = f"# Changelog\n\n## [{__version__}] - 2026-09-02\n\n- release\n"
    _write_metadata(tmp_path, changelog=changelog, citation_date="2026-09-01")

    with pytest.raises(ValueError, match="date-released does not match"):
        validate_release_metadata(f"v{__version__}", tmp_path)


def test_release_metadata_rejects_future_release_date(tmp_path: Path) -> None:
    future_date = date.today() + timedelta(days=1)
    release_date = future_date.isoformat()
    changelog = f"# Changelog\n\n## [{__version__}] - {release_date}\n\n- release\n"
    _write_metadata(tmp_path, changelog=changelog, citation_date=release_date)

    with pytest.raises(ValueError, match="in the future"):
        validate_release_metadata(f"v{__version__}", tmp_path)


def test_release_metadata_rejects_publish_day_drift(tmp_path: Path) -> None:
    metadata_date = date.today()
    release_date = metadata_date.isoformat()
    changelog = f"# Changelog\n\n## [{__version__}] - {release_date}\n\n- release\n"
    _write_metadata(tmp_path, changelog=changelog, citation_date=release_date)

    with pytest.raises(ValueError, match="does not match expected release date"):
        validate_release_metadata(
            f"v{__version__}",
            tmp_path,
            expected_date=metadata_date - timedelta(days=1),
        )


def test_cyclonedx_finalizer_is_deterministic_and_subject_bound(tmp_path: Path) -> None:
    subject = tmp_path / "permitdiff.whl"
    subject.write_bytes(b"wheel-one")
    sbom_path = tmp_path / "permitdiff-sbom.cdx.json"
    base_sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [],
    }
    sbom_path.write_text(json.dumps(base_sbom), encoding="utf-8")

    first_serial = finalize_cyclonedx_sbom(sbom_path, subject)
    first_document = json.loads(sbom_path.read_text(encoding="utf-8"))

    assert first_document["serialNumber"] == first_serial
    assert first_serial.startswith("urn:uuid:")
    uuid.UUID(first_serial.removeprefix("urn:uuid:"))

    second_serial = finalize_cyclonedx_sbom(sbom_path, subject)
    second_document = json.loads(sbom_path.read_text(encoding="utf-8"))

    assert second_serial == first_serial
    assert second_document == first_document

    subject.write_bytes(b"wheel-two")
    third_serial = finalize_cyclonedx_sbom(sbom_path, subject)
    assert third_serial != first_serial


def test_release_workflow_preserves_external_evidence() -> None:
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "scripts/validate_external_repository.py" in release_workflow
    assert "--output ../../dist/external-repository-evidence.json" in release_workflow
    assert "external-repository-evidence.json \\" in release_workflow
    assert "> SHA256SUMS" in release_workflow
    assert "sha256sum --check SHA256SUMS" in release_workflow
    assert "subject-path: |" in release_workflow
    assert "dist/external-repository-evidence.json" in release_workflow
    assert 'gh release create "$GITHUB_REF_NAME" dist/*' in release_workflow
    assert "mkdir pypi-dist" in release_workflow
    assert "cp dist/*.whl dist/*.tar.gz pypi-dist/" in release_workflow
    assert "packages-dir: pypi-dist/" in release_workflow
    assert '--expected-date "$(date -u +%F)"' in release_workflow
    assert "needs: [build, github-release]" in release_workflow


def test_release_workflow_finalizes_reproducible_cyclonedx_before_attestation() -> None:
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "--output-reproducible" in release_workflow
    assert "scripts/finalize_cyclonedx_sbom.py" in release_workflow
    assert "--subject dist/permitdiff-*.whl" in release_workflow
    assert release_workflow.index("scripts/finalize_cyclonedx_sbom.py") < release_workflow.index(
        "- name: Attest SBOM"
    )


def test_workflow_actions_are_pinned_to_commits() -> None:
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("uses:"):
                reference = stripped.removeprefix("uses:").strip()
                assert _SHA_PIN.fullmatch(reference), f"unpinned action in {workflow}: {reference}"


def test_readme_assets_are_valid_svg() -> None:
    for name in ("permitdiff-hero.svg", "permitdiff-terminal.svg"):
        # Repository-controlled SVG fixture; no untrusted XML input is parsed.
        root = ET.parse(ROOT / "docs/assets" / name).getroot()  # noqa: S314
        assert root.tag.endswith("svg")
