from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from permitdiff import __version__

ROOT = Path(__file__).resolve().parents[1]
_SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")


def test_release_metadata_uses_one_version() -> None:
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert citation["version"] == __version__
    assert f"## [{__version__}]" in changelog


def test_workflow_actions_are_pinned_to_commits() -> None:
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("uses:"):
                reference = stripped.removeprefix("uses:").strip()
                assert _SHA_PIN.fullmatch(reference), f"unpinned action in {workflow}: {reference}"


def test_readme_assets_are_valid_svg() -> None:
    for name in ("permitdiff-hero.svg", "permitdiff-terminal.svg"):
        root = ET.parse(ROOT / "docs/assets" / name).getroot()
        assert root.tag.endswith("svg")
