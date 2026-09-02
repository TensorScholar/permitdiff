from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest
import yaml

from permitdiff import __version__
from scripts.check_release import validate_release_metadata

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
    assert validate_release_metadata(f"v{__version__}", ROOT) == date(2026, 9, 2)


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
