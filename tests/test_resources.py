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
    assert "permitdiff compare" in (tmp_path / ".github/workflows/permitdiff.yml").read_text(
        encoding="utf-8"
    )


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


def test_write_starter_late_conflict_is_preflighted(tmp_path: Path) -> None:
    destination = tmp_path / "starter"
    destination.mkdir()
    conflict = destination / "permitdiff-gate.yaml"
    conflict.write_text("keep-me\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_starter(destination)

    assert conflict.read_text(encoding="utf-8") == "keep-me\n"
    assert not (destination / "policies/baseline.yaml").exists()


def test_write_starter_materialization_failure_leaves_no_partial_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "starter"
    real_write_text = Path.write_text
    writes = 0

    def fail_second_write(
        path: Path,
        data: str,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("simulated staging failure")
        return real_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_second_write)

    with pytest.raises(OSError, match="simulated staging failure"):
        write_starter(destination)

    assert not destination.exists()


def test_write_starter_force_rolls_back_partial_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "starter"
    write_starter(destination)

    baseline = destination / "policies/baseline.yaml"
    baseline.write_text("locally-customized\n", encoding="utf-8")
    before = {relative: (destination / relative).read_bytes() for relative in starter_files()}

    real_replace = Path.replace
    replacements = 0

    def fail_second_replace(path: Path, target: Path) -> Path:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("simulated publish failure")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated publish failure"):
        write_starter(destination, force=True)

    after = {relative: (destination / relative).read_bytes() for relative in starter_files()}
    assert after == before


def test_write_starter_dangling_symlink_is_preflighted(tmp_path: Path) -> None:
    destination = tmp_path / "starter"
    destination.mkdir()
    conflict = destination / "permitdiff-gate.yaml"
    conflict.symlink_to("missing-target")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_starter(destination)

    assert conflict.is_symlink()
    assert conflict.readlink() == Path("missing-target")
    assert not (destination / "policies/baseline.yaml").exists()


def test_write_starter_force_restores_dangling_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "starter"
    destination.mkdir()

    baseline = destination / "policies/baseline.yaml"
    baseline.parent.mkdir(parents=True)
    baseline.symlink_to("missing-policy")

    real_replace = Path.replace
    replacements = 0

    def fail_second_replace(path: Path, target: Path) -> Path:
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("simulated publish failure")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_second_replace)

    with pytest.raises(OSError, match="simulated publish failure"):
        write_starter(destination, force=True)

    assert baseline.is_symlink()
    assert baseline.readlink() == Path("missing-policy")
    assert not (destination / "policies/candidate.yaml").exists()


def test_write_starter_mkdir_failure_cleans_partial_parents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer = tmp_path / "outer"
    destination = outer / "inner" / "starter"
    real_mkdir = Path.mkdir

    def fail_destination_parent(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path == destination.parent:
            real_mkdir(outer, mode=mode, parents=False, exist_ok=False)
            raise OSError("simulated parent creation failure")
        real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_destination_parent)

    with pytest.raises(OSError, match="simulated parent creation failure"):
        write_starter(destination)

    assert not outer.exists()
