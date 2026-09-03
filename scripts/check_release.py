"""Validate development, prepared-release, and immutable release metadata contracts."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from permitdiff import __version__

_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:(?P<pre>a|b|rc)(?P<pre_n>0|[1-9]\d*))?"
    r"(?:\.dev(?P<dev_n>0|[1-9]\d*))?$"
)
_DATED_HEADING_RE = re.compile(
    r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})$",
    flags=re.MULTILINE,
)


def _version_key(version: str) -> tuple[int, int, int, int, int, int, int]:
    """Return a sortable key for PermitDiff's bounded PEP 440 version subset."""

    match = _VERSION_RE.fullmatch(version)
    if match is None:
        raise ValueError(
            "version must use canonical PermitDiff form X.Y.Z, X.Y.Z{a|b|rc}N, "
            "or either form followed by .devN"
        )

    release = tuple(int(match.group(name)) for name in ("major", "minor", "patch"))
    pre = match.group("pre")
    pre_n = int(match.group("pre_n") or 0)
    dev = match.group("dev_n")
    dev_n = int(dev or 0)

    if pre is None:
        phase_rank = 3 if dev is None else -1
    else:
        phase_rank = {"a": 0, "b": 1, "rc": 2}[pre]
    dev_final_rank = 0 if dev is not None else 1
    return (*release, phase_rank, pre_n, dev_final_rank, dev_n)


def _release_date_from_changelog(changelog: str, version: str) -> date:
    pattern = rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$"
    matches = re.findall(pattern, changelog, flags=re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(
            f"CHANGELOG.md must contain exactly one dated entry for {version}; found {len(matches)}"
        )
    try:
        release_date = date.fromisoformat(matches[0])
    except ValueError as exc:  # pragma: no cover - regex already constrains the shape
        raise ValueError(f"CHANGELOG.md has an invalid release date for {version}") from exc
    if release_date > date.today():
        raise ValueError(f"CHANGELOG.md release date {release_date} is in the future")
    return release_date


def _read_citation(root: Path) -> dict[str, Any]:
    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    if not isinstance(citation, dict):
        raise ValueError("CITATION.cff must contain a mapping")
    return citation


def validate_release_metadata(
    tag: str,
    root: Path = Path("."),
    *,
    expected_date: date | None = None,
    package_version: str = __version__,
) -> date:
    """Validate immutable release identity across tag, changelog, and citation metadata."""

    _version_key(package_version)
    if ".dev" in package_version:
        raise ValueError("development package versions cannot be published as releases")

    expected_tag = f"v{package_version}"
    if tag != expected_tag:
        raise ValueError(f"tag {tag!r} does not match expected release tag {expected_tag!r}")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    release_date = _release_date_from_changelog(changelog, package_version)

    citation = _read_citation(root)
    if str(citation.get("version")) != package_version:
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


def validate_prepared_release_metadata(
    root: Path = Path("."),
    *,
    package_version: str = __version__,
) -> date:
    """Validate a release-preparation tree before its immutable tag exists."""

    return validate_release_metadata(
        f"v{package_version}",
        root,
        package_version=package_version,
    )


def validate_development_metadata(
    root: Path = Path("."),
    *,
    package_version: str = __version__,
) -> str:
    """Validate that mutable source uses a forward dev identity without rewriting release evidence."""

    package_key = _version_key(package_version)
    if ".dev" not in package_version:
        raise ValueError("development source version must include a .devN suffix")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if len(re.findall(r"^## \[Unreleased\]$", changelog, flags=re.MULTILINE)) != 1:
        raise ValueError("CHANGELOG.md must contain exactly one [Unreleased] section")
    if re.search(
        rf"^## \[{re.escape(package_version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
        changelog,
        flags=re.MULTILINE,
    ):
        raise ValueError("development package version must not have a dated changelog entry")

    citation = _read_citation(root)
    citation_version = str(citation.get("version") or "")
    if not citation_version:
        raise ValueError("CITATION.cff must declare the latest released version")
    if citation_version == package_version:
        raise ValueError("development package identity must differ from the cited released version")
    citation_key = _version_key(citation_version)
    if package_key <= citation_key:
        raise ValueError(
            f"development version {package_version} must sort after released version {citation_version}"
        )

    dated_entries = _DATED_HEADING_RE.findall(changelog)
    if not dated_entries:
        raise ValueError("CHANGELOG.md must contain at least one dated release entry")
    latest_changelog_version = dated_entries[0][0]
    if latest_changelog_version != citation_version:
        raise ValueError(
            "CITATION.cff must identify the latest dated release in CHANGELOG.md; "
            f"found citation {citation_version!r} and latest changelog {latest_changelog_version!r}"
        )

    release_date = _release_date_from_changelog(changelog, citation_version)
    if str(citation.get("date-released")) != release_date.isoformat():
        raise ValueError(
            "CITATION.cff date-released does not match the latest dated CHANGELOG.md release"
        )

    return citation_version


def validate_source_metadata(
    root: Path = Path("."),
    *,
    package_version: str = __version__,
) -> str:
    """Validate either the normal dev state or the short-lived prepared-release state."""

    if ".dev" in package_version:
        validate_development_metadata(root, package_version=package_version)
        return "development"
    validate_prepared_release_metadata(root, package_version=package_version)
    return "prepared-release"


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tag")
    mode.add_argument(
        "--development",
        action="store_true",
        help="Validate normal mutable source-tree identity after a release.",
    )
    mode.add_argument(
        "--prepared",
        action="store_true",
        help="Validate a final-version release-preparation tree before tagging.",
    )
    mode.add_argument(
        "--source",
        action="store_true",
        help="Validate either development or prepared-release source state.",
    )
    parser.add_argument(
        "--expected-date",
        help="Require release metadata date to equal this ISO date (YYYY-MM-DD).",
    )
    args = parser.parse_args()

    if (args.development or args.prepared or args.source) and args.expected_date is not None:
        raise SystemExit("--expected-date is valid only with --tag")

    expected_date: date | None = None
    if args.expected_date is not None:
        try:
            expected_date = date.fromisoformat(args.expected_date)
        except ValueError as exc:
            raise SystemExit("--expected-date must be an ISO date in YYYY-MM-DD form") from exc

    try:
        if args.development:
            released_version = validate_development_metadata()
            print(
                f"development metadata valid for {__version__} (latest release {released_version})"
            )
        elif args.prepared:
            release_date = validate_prepared_release_metadata()
            print(
                f"prepared release metadata valid for v{__version__} ({release_date.isoformat()})"
            )
        elif args.source:
            source_state = validate_source_metadata()
            print(f"source metadata valid for {__version__} ({source_state})")
        else:
            release_date = validate_release_metadata(args.tag, expected_date=expected_date)
            print(f"release metadata valid for {args.tag} ({release_date.isoformat()})")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
