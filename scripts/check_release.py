"""Validate release metadata before publishing."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import yaml

from permitdiff import __version__


def _release_date_from_changelog(changelog: str) -> date:
    pattern = rf"^## \[{re.escape(__version__)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$"
    matches = re.findall(pattern, changelog, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(
            f"CHANGELOG.md must contain exactly one dated entry for {__version__}; "
            f"found {len(matches)}"
        )
    try:
        release_date = date.fromisoformat(matches[0])
    except ValueError as exc:  # pragma: no cover - regex already constrains the shape
        raise ValueError(f"CHANGELOG.md has an invalid release date for {__version__}") from exc
    if release_date > date.today():
        raise ValueError(f"CHANGELOG.md release date {release_date} is in the future")
    return release_date


def validate_release_metadata(
    tag: str,
    root: Path = Path("."),
    *,
    expected_date: date | None = None,
) -> date:
    """Validate immutable release identity across tag, changelog, and citation metadata."""

    expected_tag = f"v{__version__}"
    if tag != expected_tag:
        raise ValueError(f"tag {tag!r} does not match expected release tag {expected_tag!r}")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    release_date = _release_date_from_changelog(changelog)

    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    if not isinstance(citation, dict):
        raise ValueError("CITATION.cff must contain a mapping")
    if citation.get("version") != __version__:
        raise ValueError("CITATION.cff version does not match the package version")

    citation_date = citation.get("date-released")
    if str(citation_date) != release_date.isoformat():
        raise ValueError(
            "CITATION.cff date-released does not match the dated CHANGELOG.md release entry"
        )

    if expected_date is not None and release_date != expected_date:
        raise ValueError(
            f"release metadata date {release_date} does not match expected release date "
            f"{expected_date}"
        )

    return release_date


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--expected-date",
        help="Require the release metadata date to equal this ISO date (YYYY-MM-DD).",
    )
    args = parser.parse_args()

    expected_date: date | None = None
    if args.expected_date is not None:
        try:
            expected_date = date.fromisoformat(args.expected_date)
        except ValueError as exc:
            raise SystemExit("--expected-date must be an ISO date in YYYY-MM-DD form") from exc

    try:
        release_date = validate_release_metadata(args.tag, expected_date=expected_date)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"release metadata valid for {args.tag} ({release_date.isoformat()})")


if __name__ == "__main__":
    main()
