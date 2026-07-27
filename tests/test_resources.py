from __future__ import annotations

from pathlib import Path

import pytest

from permitdiff.resources import starter_files, write_starter


def test_starter_inventory_is_stable() -> None:
    assert starter_files() == (
        "policies/baseline.yaml",
        "policies/candidate.yaml",
        "corpus.jsonl",
        "permitdiff-gate.yaml",
        ".github/workflows/permitdiff.yml",
    )


def test_write_starter_materializes_runnable_project(tmp_path: Path) -> None:
    written = write_starter(tmp_path)
    assert {path.relative_to(tmp_path).as_posix() for path in written} == set(starter_files())
    assert (tmp_path / "policies/baseline.yaml").is_file()
    assert "permitdiff compare" in (
        tmp_path / ".github/workflows/permitdiff.yml"
    ).read_text(encoding="utf-8")


def test_write_starter_refuses_overwrite_without_force(tmp_path: Path) -> None:
    write_starter(tmp_path)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_starter(tmp_path)
    assert len(write_starter(tmp_path, force=True)) == len(starter_files())


def test_repository_examples_match_packaged_starter() -> None:
    root = Path(__file__).resolve().parents[1]
    pairs = {
        root / "examples/baseline.yaml": (
            root / "src/permitdiff/data/starter/policies/baseline.yaml"
        ),
        root / "examples/candidate.yaml": (
            root / "src/permitdiff/data/starter/policies/candidate.yaml"
        ),
        root / "examples/corpus.jsonl": root / "src/permitdiff/data/starter/corpus.jsonl",
        root / "examples/gate.yaml": root / "src/permitdiff/data/starter/permitdiff-gate.yaml",
    }
    for example, starter in pairs.items():
        assert example.read_bytes() == starter.read_bytes()
