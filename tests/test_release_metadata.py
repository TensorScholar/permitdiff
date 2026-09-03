from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

from permitdiff import __version__
from scripts.check_release import (
    _latest_released_version,
    validate_development_metadata,
    validate_release_metadata,
    validate_source_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")


def test_current_development_metadata_is_valid() -> None:
    latest = validate_development_metadata(ROOT)

    assert latest == "0.1.0rc2"
    assert __version__ == "0.1.0rc3.dev0"


def test_source_metadata_auto_detects_current_development_state() -> None:
    state = validate_source_metadata(ROOT)

    assert state == "development"


def test_development_metadata_rejects_reused_released_version(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc2"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0rc2] - 2026-09-02\n",
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc2"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must use a .devN version"):
        validate_development_metadata(tmp_path)


def test_development_metadata_rejects_missing_unreleased_section(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc3.dev0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc2] - 2026-09-02\n", encoding="utf-8"
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc2"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"exactly one \[Unreleased\] section"):
        validate_development_metadata(tmp_path)


def test_development_metadata_rejects_non_forward_version(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc2.dev1"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0rc2] - 2026-09-02\n",
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc2"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must advance beyond latest release"):
        validate_development_metadata(tmp_path)


def test_development_metadata_rejects_stale_citation(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc3.dev0"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.0rc2] - 2026-09-02\n",
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc1"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="CITATION.cff must describe latest release"):
        validate_development_metadata(tmp_path)


def test_source_metadata_accepts_prepared_release(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc3"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc3] - 2026-09-03\n\n## [0.1.0rc2] - 2026-09-02\n",
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc3"\ndate-released: 2026-09-03\n',
        encoding="utf-8",
    )

    assert validate_source_metadata(tmp_path) == "prepared-release"


def test_source_metadata_does_not_accept_stale_final_version(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc2"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc2] - 2026-09-02\n", encoding="utf-8"
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc2"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must be newer than latest prior release"):
        validate_source_metadata(tmp_path)


def test_release_metadata_matches_tag_and_date() -> None:
    version, released = validate_release_metadata(ROOT, "v0.1.0rc2")

    assert version == "0.1.0rc2"
    assert released == date(2026, 9, 2)


def test_release_metadata_can_require_publish_day() -> None:
    version, released = validate_release_metadata(
        ROOT,
        "v0.1.0rc2",
        expected_release_date=date(2026, 9, 2),
    )

    assert version == "0.1.0rc2"
    assert released == date(2026, 9, 2)


def test_release_metadata_rejects_wrong_tag(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc1"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc1] - 2026-09-02\n", encoding="utf-8"
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc1"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="release tag mismatch"):
        validate_release_metadata(tmp_path, "v0.1.0rc2")


def test_release_metadata_rejects_duplicate_changelog_entry(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc1"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc1] - 2026-09-02\n\n## [0.1.0rc1] - 2026-09-02\n",
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc1"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exactly one dated changelog entry"):
        validate_release_metadata(tmp_path, "v0.1.0rc1")


def test_release_metadata_rejects_citation_date_drift(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc1"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc1] - 2026-09-02\n", encoding="utf-8"
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc1"\ndate-released: 2026-09-01\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="release-date mismatch"):
        validate_release_metadata(tmp_path, "v0.1.0rc1")


def test_release_metadata_rejects_wrong_publish_day(tmp_path: Path) -> None:
    (tmp_path / "src/permitdiff").mkdir(parents=True)
    (tmp_path / "src/permitdiff/_version.py").write_text(
        '__version__ = "0.1.0rc1"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.1.0rc1] - 2026-09-02\n", encoding="utf-8"
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "0.1.0rc1"\ndate-released: 2026-09-02\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="publish-day mismatch"):
        validate_release_metadata(
            tmp_path,
            "v0.1.0rc1",
            expected_release_date=date(2026, 9, 3),
        )


def test_latest_released_version_ignores_unreleased() -> None:
    changelog = """# Changelog

## [Unreleased]

## [0.2.0] - 2026-09-03

## [0.1.0] - 2026-09-02
"""

    assert _latest_released_version(changelog) == ("0.2.0", date(2026, 9, 3))


def test_latest_released_version_rejects_missing_release() -> None:
    with pytest.raises(ValueError, match="no dated release entries"):
        _latest_released_version("# Changelog\n\n## [Unreleased]\n")


def test_release_workflow_uses_oidc_and_attestations() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "id-token: write" in workflow
    assert "attest-build-provenance" in workflow
    assert "attest-sbom" in workflow
    assert "pypa/gh-action-pypi-publish" in workflow
    assert "environment: pypi" in workflow


def test_release_workflow_creates_github_release_before_pypi() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "needs: build" in workflow
    assert "needs: github-release" in workflow
    assert workflow.index("github-release:") < workflow.index("publish-pypi:")


def test_release_workflow_marks_prerelease_tags() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "PRERELEASE_FLAG=--prerelease" in workflow
    assert 'gh release create "$GITHUB_REF_NAME"' in workflow
    assert "$PRERELEASE_FLAG" in workflow


def test_release_workflow_stages_only_python_distributions_for_pypi() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "mkdir -p publish-dist" in workflow
    assert 'cp dist/*.whl dist/*.tar.gz publish-dist/' in workflow
    assert "packages-dir: publish-dist/" in workflow


def test_release_workflow_preserves_external_execution_evidence() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "scripts/validate_external_repository.py" in workflow
    assert "external-repository-evidence.json" in workflow
    assert "external-repository-evidence.json" in workflow.split("SHA256SUMS", maxsplit=1)[0]
    assert "external-repository-evidence.json" in workflow.split("subject-path:", maxsplit=1)[1]


def test_release_workflow_finalizes_reproducible_cyclonedx_before_attestation() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "--output-reproducible" in workflow
    assert "scripts/finalize_cyclonedx_sbom.py" in workflow
    assert "--subject dist/permitdiff-*.whl" in workflow
    assert workflow.index("scripts/finalize_cyclonedx_sbom.py") < workflow.index(
        "- name: Attest SBOM"
    )


def test_ci_distinguishes_development_and_release_preparation() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert '"$HEAD_REF" == release/prepare-*' in workflow
    assert "python scripts/check_release.py --prepared" in workflow
    assert "python scripts/check_release.py --source" in workflow
    assert "python scripts/check_release.py --development" in workflow
    assert "Rehearse release metadata contract" not in workflow


def test_workflow_actions_are_pinned_to_commits() -> None:
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("uses:"):
                reference = stripped.removeprefix("uses:").strip()
                if reference == "./":
                    continue
                assert _SHA_PIN.fullmatch(reference), f"unpinned action in {workflow}: {reference}"


def test_readme_assets_are_valid_svg() -> None:
    for name in ("permitdiff-hero.svg", "permitdiff-terminal.svg"):
        # Repository-controlled SVG fixture; no untrusted XML input is parsed.
        root = ET.parse(ROOT / "docs/assets" / name).getroot()  # noqa: S314
        assert root.tag.endswith("svg")
