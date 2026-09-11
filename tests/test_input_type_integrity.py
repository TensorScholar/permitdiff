from __future__ import annotations

import json
from pathlib import Path

import pytest

from permitdiff.corpus import load_corpus
from permitdiff.errors import CorpusLoadError, GateLoadError, PolicyLoadError
from permitdiff.gate import GateConfig
from permitdiff.policy import PolicyDocument


def test_corpus_rejects_string_trust_marker(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    scenario = {
        "id": "string-trust",
        "action": {
            "principal": "p",
            "agent": "a",
            "tool": "t",
            "context": {"security_metadata_trusted": "true"},
        },
    }
    path.write_text(json.dumps(scenario) + "\n", encoding="utf-8")

    with pytest.raises(CorpusLoadError, match="security_metadata_trusted"):
        load_corpus(path)


def test_corpus_rejects_string_annotation_boolean(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    scenario = {
        "id": "string-annotation",
        "action": {
            "principal": "p",
            "agent": "a",
            "tool": "t",
            "annotations": {"read_only": "false"},
        },
    }
    path.write_text(json.dumps(scenario) + "\n", encoding="utf-8")

    with pytest.raises(CorpusLoadError, match="read_only"):
        load_corpus(path)


@pytest.mark.parametrize(
    "unsafe_scalar",
    [
        "max_privilege_expansions: true",
        'forbid_default_effect_relaxation: "false"',
    ],
)
def test_gate_rejects_coercive_security_scalars(tmp_path: Path, unsafe_scalar: str) -> None:
    path = tmp_path / "gate.yaml"
    path.write_text(
        "\n".join(
            [
                "api_version: permitdiff.dev/v1alpha1",
                "kind: Gate",
                unsafe_scalar,
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(GateLoadError):
        GateConfig.from_yaml(path)


def test_policy_rejects_quoted_annotation_boolean(tmp_path: Path) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(
        """api_version: permitdiff.dev/v1alpha1
kind: Policy
metadata:
  name: strict-types
  version: "1.0.0"
default_effect: deny
rules:
  - id: unsafe-read
    description: Quoted booleans must not cross the policy trust boundary.
    effect: allow
    match:
      security_metadata_trusted: true
      read_only: "true"
""",
        encoding="utf-8",
    )

    with pytest.raises(PolicyLoadError, match="read_only"):
        PolicyDocument.from_yaml(path)
