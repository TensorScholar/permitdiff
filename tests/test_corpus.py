from __future__ import annotations

import json
from pathlib import Path

import pytest

from permitdiff.corpus import load_corpus
from permitdiff.errors import CorpusLoadError


def test_loads_jsonl_and_preserves_order(scenarios: list) -> None:
    assert [item.id for item in scenarios][:2] == ["customer-read", "refund-50"]


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    scenario = {
        "id": "one",
        "action": {"principal": "p", "agent": "a", "tool": "t"},
    }
    path.write_text("\n" + json.dumps(scenario) + "\n\n", encoding="utf-8")
    assert len(load_corpus(path)) == 1


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    scenario = {
        "id": "duplicate",
        "action": {"principal": "p", "agent": "a", "tool": "t"},
    }
    encoded = json.dumps(scenario)
    path.write_text(f"{encoded}\n{encoded}\n", encoding="utf-8")
    with pytest.raises(CorpusLoadError, match="duplicate scenario"):
        load_corpus(path)


def test_invalid_json_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    valid = {
        "id": "first",
        "action": {"principal": "p", "agent": "a", "tool": "t"},
    }
    path.write_text(json.dumps(valid) + "\nnot-json\n", encoding="utf-8")
    with pytest.raises(CorpusLoadError, match="line 2"):
        load_corpus(path)


def test_empty_corpus_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(CorpusLoadError, match="at least one"):
        load_corpus(path)


def test_missing_corpus_is_wrapped(tmp_path: Path) -> None:
    with pytest.raises(CorpusLoadError, match="failed to load corpus"):
        load_corpus(tmp_path / "missing.jsonl")
