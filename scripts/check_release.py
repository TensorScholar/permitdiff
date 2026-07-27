"""Validate release metadata before publishing."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from permitdiff import __version__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    tag_version = args.tag.removeprefix("v")
    if tag_version != __version__:
        raise SystemExit(f"tag {args.tag!r} does not match package version {__version__!r}")

    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    pattern = rf"^## \[{re.escape(__version__)}\]"
    if re.search(pattern, changelog, flags=re.MULTILINE) is None:
        raise SystemExit(f"CHANGELOG.md has no entry for {__version__}")

    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    if citation.get("version") != __version__:
        raise SystemExit("CITATION.cff version does not match the package version")

    print(f"release metadata valid for {args.tag}")


if __name__ == "__main__":
    main()
