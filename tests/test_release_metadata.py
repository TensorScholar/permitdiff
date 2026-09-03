from __future__ import annotations

import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from scripts.check_release import (
    validate_development_metadata,
    validate_prepared_release_metadata,
    validate_release_metadata,
    validate_source_metadata,
)
from scripts.finalize_cyclonedx_sbom import finalize_cyclonedx_sbom

from permitdiff import __version__

ROOT = Path(__file__).resolve().parents[1]
_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")
_RELEASE_VERSION = "1.2.3rc4"
_RELEASE_DATE = "2026-09-02"


def _write_metadata(
    root: Path,
    *,
    changelog: str,
    citation_version: str,
    citation_date: str,
) -> None:
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (root / "CITATION.cff").write_text(
        "\n".join(
            [
                "cff-version: 1.2.0",
                'title: "PermitDiff"',
                f"version: {citation_version}",
                f"date-released: {citation_date}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _release_changelog(version: str = _RELEASE_VERSION, released: str = _RELEASE_DATE) -> str:
    return f"# Changelog\n\n## [{version}] - {released}\n\n- release\n"


def test_current_development_metadata_is_coherent() -> None:
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    released_version = validate_development_metadata(ROOT)

    assert ".dev" in __version__
    assert released_version == str(citation["version"])
    assert "## [Unreleased]" in changelog
    assert f"## [{__version__}] - " not in changelog
    assert released_version != __version__
    assert validate_source_metadata(ROOT) == "development"


def test_release_metadata_accepts_coherent_release(tmp_path: Path) -> None:
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(),
        citation_version=_RELEASE_VERSION,
        citation_date=_RELEASE_DATE,
    )

    release_date = validate_release_metadata(
        f"v{_RELEASE_VERSION}",
        tmp_path,
        package_version=_RELEASE_VERSION,
    )

    assert release_date.isoformat() == _RELEASE_DATE


def test_prepared_release_and_source_state_accept_coherent_final_tree(tmp_path: Path) -> None:
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(),
        citation_version=_RELEASE_VERSION,
        citation_date=_RELEASE_DATE,
    )

    release_date = validate_prepared_release_metadata(
        tmp_path,
        package_version=_RELEASE_VERSION,
    )

    assert release_date.isoformat() == _RELEASE_DATE
    assert (
        validate_source_metadata(tmp_path, package_version=_RELEASE_VERSION) == "prepared-release"
    )


def test_release_metadata_rejects_noncanonical_tag(tmp_path: Path) -> None:
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(),
        citation_version=_RELEASE_VERSION,
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="expected release tag"):
        validate_release_metadata(
            _RELEASE_VERSION,
            tmp_path,
            package_version=_RELEASE_VERSION,
        )


def test_release_metadata_rejects_development_identity(tmp_path: Path) -> None:
    development_version = "1.2.3rc5.dev0"
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(development_version),
        citation_version=development_version,
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="development package versions cannot be published"):
        validate_release_metadata(
            f"v{development_version}",
            tmp_path,
            package_version=development_version,
        )


def test_release_metadata_rejects_duplicate_changelog_entries(tmp_path: Path) -> None:
    changelog = "\n".join(
        [
            "# Changelog",
            "",
            f"## [{_RELEASE_VERSION}] - {_RELEASE_DATE}",
            "",
            "- first",
            "",
            f"## [{_RELEASE_VERSION}] - {_RELEASE_DATE}",
            "",
            "- duplicate",
            "",
        ]
    )
    _write_metadata(
        tmp_path,
        changelog=changelog,
        citation_version=_RELEASE_VERSION,
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="exactly one dated entry"):
        validate_release_metadata(
            f"v{_RELEASE_VERSION}",
            tmp_path,
            package_version=_RELEASE_VERSION,
        )


def test_release_metadata_rejects_citation_date_drift(tmp_path: Path) -> None:
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(),
        citation_version=_RELEASE_VERSION,
        citation_date="2026-09-01",
    )

    with pytest.raises(ValueError, match="date-released does not match"):
        validate_release_metadata(
            f"v{_RELEASE_VERSION}",
            tmp_path,
            package_version=_RELEASE_VERSION,
        )


def test_release_metadata_rejects_future_release_date(tmp_path: Path) -> None:
    release_date = (date.today() + timedelta(days=1)).isoformat()
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(released=release_date),
        citation_version=_RELEASE_VERSION,
        citation_date=release_date,
    )

    with pytest.raises(ValueError, match="in the future"):
        validate_release_metadata(
            f"v{_RELEASE_VERSION}",
            tmp_path,
            package_version=_RELEASE_VERSION,
        )


def test_release_metadata_rejects_publish_day_drift(tmp_path: Path) -> None:
    metadata_date = date.today()
    release_date = metadata_date.isoformat()
    _write_metadata(
        tmp_path,
        changelog=_release_changelog(released=release_date),
        citation_version=_RELEASE_VERSION,
        citation_date=release_date,
    )

    with pytest.raises(ValueError, match="does not match expected release date"):
        validate_release_metadata(
            f"v{_RELEASE_VERSION}",
            tmp_path,
            package_version=_RELEASE_VERSION,
            expected_date=metadata_date - timedelta(days=1),
        )


def test_development_metadata_rejects_missing_unreleased_section(tmp_path: Path) -> None:
    _write_metadata(
        tmp_path,
        changelog=_release_changelog("1.2.3rc4"),
        citation_version="1.2.3rc4",
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="exactly one \[Unreleased\] section"):
        validate_development_metadata(tmp_path, package_version="1.2.3rc5.dev0")


def test_development_metadata_rejects_non_forward_version(tmp_path: Path) -> None:
    changelog = (
        "# Changelog\n\n## [Unreleased]\n\n- next\n\n## [1.2.3rc4] - 2026-09-02\n\n- release\n"
    )
    _write_metadata(
        tmp_path,
        changelog=changelog,
        citation_version="1.2.3rc4",
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="must sort after released version"):
        validate_development_metadata(tmp_path, package_version="1.2.3rc3.dev0")


def test_development_metadata_rejects_stale_citation(tmp_path: Path) -> None:
    changelog = (
        "# Changelog\n\n## [Unreleased]\n\n- next\n\n"
        "## [1.2.3rc5] - 2026-09-03\n\n- newer\n\n"
        "## [1.2.3rc4] - 2026-09-02\n\n- older\n"
    )
    _write_metadata(
        tmp_path,
        changelog=changelog,
        citation_version="1.2.3rc4",
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="latest dated release"):
        validate_development_metadata(tmp_path, package_version="1.2.3rc6.dev0")


def test_development_metadata_rejects_dated_dev_version(tmp_path: Path) -> None:
    changelog = (
        "# Changelog\n\n## [Unreleased]\n\n- next\n\n"
        "## [1.2.3rc5.dev0] - 2026-09-03\n\n- invalid dev release\n\n"
        "## [1.2.3rc4] - 2026-09-02\n\n- release\n"
    )
    _write_metadata(
        tmp_path,
        changelog=changelog,
        citation_version="1.2.3rc4",
        citation_date=_RELEASE_DATE,
    )

    with pytest.raises(ValueError, match="must not have a dated changelog entry"):
        validate_development_metadata(tmp_path, package_version="1.2.3rc5.dev0")


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


def test_prerelease_tags_are_marked_as_github_prereleases() -> None:
    release_workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "release_args=(--generate-notes --verify-tag)" in release_workflow
    assert '[[ "$GITHUB_REF_NAME" =~ (a|b|rc)[0-9]+$ ]]' in release_workflow
    assert "release_args+=(--prerelease)" in release_workflow
    assert 'gh release create "$GITHUB_REF_NAME" dist/* "${release_args[@]}"' in release_workflow


def test_ci_enforces_branch_aware_source_lifecycle() -> None:
    ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert '"$HEAD_REF" == release/prepare-*' in ci_workflow
    assert "python scripts/check_release.py --prepared" in ci_workflow
    assert "python scripts/check_release.py --source" in ci_workflow
    assert "python scripts/check_release.py --development" in ci_workflow
    assert "Rehearse release metadata contract" not in ci_workflow


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
