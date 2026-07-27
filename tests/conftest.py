from __future__ import annotations

from pathlib import Path

import pytest

from permitdiff.corpus import load_corpus
from permitdiff.models import Scenario
from permitdiff.policy import PolicyDocument

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def baseline() -> PolicyDocument:
    return PolicyDocument.from_yaml(ROOT / "examples" / "baseline.yaml")


@pytest.fixture
def candidate() -> PolicyDocument:
    return PolicyDocument.from_yaml(ROOT / "examples" / "candidate.yaml")


@pytest.fixture
def scenarios() -> list[Scenario]:
    return load_corpus(ROOT / "examples" / "corpus.jsonl")
