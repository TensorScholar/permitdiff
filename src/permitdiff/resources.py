"""Immutable package resources and starter-project materialization."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_STARTER_FILES = (
    "policies/baseline.yaml",
    "policies/candidate.yaml",
    "corpus.jsonl",
    "permitdiff-gate.yaml",
    ".github/workflows/permitdiff.yml",
)


def starter_files() -> tuple[str, ...]:
    """Return the stable starter-project file inventory."""

    return _STARTER_FILES


def write_starter(destination: str | Path, *, force: bool = False) -> list[Path]:
    """Write the packaged starter project without touching unrelated files."""

    target = Path(destination)
    root = files("permitdiff").joinpath("data/starter")
    written: list[Path] = []
    for relative in _STARTER_FILES:
        output = target / relative
        if output.exists() and not force:
            raise FileExistsError(f"refusing to overwrite existing file: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        content = root.joinpath(relative).read_text(encoding="utf-8")
        output.write_text(content, encoding="utf-8")
        written.append(output)
    return written
