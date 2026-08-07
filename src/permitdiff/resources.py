"""Immutable package resources and starter-project materialization."""

from __future__ import annotations

import shutil
from contextlib import suppress
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

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


def _missing_directories(path: Path) -> list[Path]:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    return missing


def _remove_empty_directories(paths: list[Path]) -> None:
    for path in paths:
        with suppress(OSError):
            path.rmdir()


def write_starter(destination: str | Path, *, force: bool = False) -> list[Path]:
    """Write the packaged starter project as a failure-atomic transaction."""

    target = Path(destination)
    root = files("permitdiff").joinpath("data/starter")
    outputs = [target / relative for relative in _STARTER_FILES]

    if target.exists() and not target.is_dir():
        raise NotADirectoryError(f"starter destination is not a directory: {target}")

    if not force:
        for output in outputs:
            if output.exists():
                raise FileExistsError(f"refusing to overwrite existing file: {output}")

    # Read every packaged resource before mutating the destination.
    contents = {
        relative: root.joinpath(relative).read_text(encoding="utf-8") for relative in _STARTER_FILES
    }

    missing_parent_dirs = _missing_directories(target.parent)
    staging_parent = target.parent if target.parent.exists() else missing_parent_dirs[-1].parent

    with TemporaryDirectory(
        prefix=f".{target.name}.permitdiff-",
        dir=staging_parent,
    ) as temporary:
        staging = Path(temporary)

        # Fully materialize the replacement set before publishing anything.
        for relative, content in contents.items():
            staged = staging / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(content, encoding="utf-8")

        created_dirs: list[Path] = []
        backups: dict[Path, Path] = {}
        applied: list[tuple[Path, bool]] = []

        try:
            if missing_parent_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
                created_dirs.extend(missing_parent_dirs)

            # A new project can be published with one same-filesystem rename.
            if not target.exists():
                staging.replace(target)
                return outputs

            # Existing destinations retain unrelated files. Prepare every backup
            # before the first replacement, then roll back all applied files if
            # any commit operation fails.
            for relative, output in zip(_STARTER_FILES, outputs, strict=True):
                if output.exists() and output.is_dir():
                    raise IsADirectoryError(f"starter file path is an existing directory: {output}")

                if output.exists():
                    backup = staging / ".backup" / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(output, backup, follow_symlinks=False)
                    backups[output] = backup

            for relative, output in zip(_STARTER_FILES, outputs, strict=True):
                missing_output_dirs = _missing_directories(output.parent)
                if missing_output_dirs:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    created_dirs.extend(missing_output_dirs)

                existed = output.exists()
                (staging / relative).replace(output)
                applied.append((output, existed))

        except OSError as exc:
            rollback_error: OSError | None = None

            for output, existed in reversed(applied):
                try:
                    if existed:
                        backups[output].replace(output)
                    else:
                        output.unlink(missing_ok=True)
                except OSError as restore_exc:
                    rollback_error = restore_exc

            _remove_empty_directories(created_dirs)

            if rollback_error is not None:
                raise OSError(
                    f"starter write failed and rollback also failed: {rollback_error}"
                ) from exc
            raise

    return outputs
