"""Streaming JSONL scenario corpus loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from permitdiff.errors import CorpusLoadError
from permitdiff.models import Scenario

_MAX_CORPUS_BYTES = 50_000_000
_MAX_SCENARIOS = 100_000


def load_corpus(path: str | Path) -> list[Scenario]:
    """Load a bounded UTF-8 JSONL corpus with unique scenario identifiers."""

    corpus_path = Path(path)
    try:
        if corpus_path.stat().st_size > _MAX_CORPUS_BYTES:
            raise ValueError(f"corpus exceeds {_MAX_CORPUS_BYTES} bytes")
        scenarios: list[Scenario] = []
        seen: set[str] = set()
        with corpus_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                if len(scenarios) >= _MAX_SCENARIOS:
                    raise ValueError(f"corpus exceeds {_MAX_SCENARIOS} scenarios")
                try:
                    raw = json.loads(line)
                    scenario = Scenario.model_validate(raw)
                except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                    raise ValueError(f"line {line_number}: {exc}") from exc
                if scenario.id in seen:
                    raise ValueError(f"line {line_number}: duplicate scenario id {scenario.id!r}")
                seen.add(scenario.id)
                scenarios.append(scenario)
        if not scenarios:
            raise ValueError("corpus must contain at least one scenario")
        return scenarios
    except (OSError, UnicodeError, ValueError) as exc:
        raise CorpusLoadError(f"failed to load corpus {corpus_path}: {exc}") from exc
