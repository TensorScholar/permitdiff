"""Packet B Phase B0+B1 migration guardrails and thin lineage CLI tests.

All fixtures are synthetic. No GitHub access, no tokens, no discovery,
no real R3 evidence. Writes go only to ``tmp_path`` fixtures.

B0 guardrails:
- CB-01 lineage tooling imports no network / GitHub / PermitDiff runtime.
- No files are created under ``validation/r3-benchmark/exploratory/``.
- v1 / legacy shapes are rejected where CB-01 v2 artifacts are expected.
- Operational producers are not yet migrated (documents B0+B1 scope).

B1 CLI tests use independent frozen formulas for fixtures (hashlib
directly, not the implementation under test as oracle):
- selection_key = SHA256(url + '\\n' + baseline + '\\n' + candidate + '\\n' + path)
- transition_id = "gh-" + selection_key[:20]
- canonical url = https://github.com/<full_name>
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
import scripts.r3_cb01_corpus_construction as cb01
from scripts.build_r3_cb01_lineage import build_lineage, main
from scripts.r3_cb01_corpus_construction import CB01ConstructionError

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    ROOT
    / "validation"
    / "r3-benchmark"
    / "exploratory"
    / "cb01-corpus-construction-contract-v1.json"
)
CB01_MODULE_PATH = ROOT / "scripts" / "r3_cb01_corpus_construction.py"
LINEAGE_CLI_PATH = ROOT / "scripts" / "build_r3_cb01_lineage.py"
EXPLORATORY_DIR = ROOT / "validation" / "r3-benchmark" / "exploratory"

_ALLOWED_PATHS = (".claude/settings.json", ".claude/settings.local.json")
_VALID_BASELINE = "a" * 40
_VALID_CANDIDATE = "b" * 40
_VALID_REPO = "org/b1-valid"
_VALID_STUDY = "0123456789abcdef0123456789abcdef01234567"
_REVIEWER = "b1-reviewer"
_RATIONALE = "b1 output-blind rationale with sufficient semantics"
_INSTRUCTIONS = "b1 synthetic instructions"

_ALLOWLISTED_EXPLORATORY = frozenset(
    {
        "README.md",
        "cb01-corpus-construction-contract-v1.json",
        "freeze-completion-contract-v1.json",
        "manifest.example.json",
        "measurement-contract-v2.json",
        "permitdiff-execution-environment-v1.json",
        "pre-discovery-hardening-contract-v1.json",
        "r3-build-requirements-v1.lock",
        "r3-runtime-requirements-v1.lock",
        "reviewer-protocol-v1.json",
        "selection-plan.json",
    }
)


def _frozen_url(repo: str) -> str:
    return f"https://github.com/{repo}"


def _frozen_key(url: str, baseline: str, candidate: str, path: str) -> str:
    return hashlib.sha256(f"{url}\n{baseline}\n{candidate}\n{path}".encode()).hexdigest()


def _frozen_tid(url: str, baseline: str, candidate: str, path: str) -> str:
    return "gh-" + _frozen_key(url, baseline, candidate, path)[:20]


def _load_contract() -> tuple[dict[str, Any], bytes]:
    raw_bytes = CONTRACT_PATH.read_bytes()
    contract = json.loads(raw_bytes)
    assert isinstance(contract, dict)
    return contract, raw_bytes


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _queries_from_contract(contract: dict[str, Any]) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for entry in contract["search_frame"]:
        queries.append(
            {
                "query_id": entry["query_id"],
                "concept": entry["concept"],
                "candidate_path": entry["candidate_path"],
                "api_query": entry["api_query"],
                "reported_total_count": 0,
                "retrieved_count": 0,
                "exact_candidate_path_count": 0,
                "incomplete_results": False,
                "api_result_cap_reached": False,
            }
        )
    return queries


def _make_transition(
    *,
    repo: str = _VALID_REPO,
    baseline: str = _VALID_BASELINE,
    candidate: str = _VALID_CANDIDATE,
    path: str = ".claude/settings.json",
) -> dict[str, Any]:
    url = _frozen_url(repo)
    key = _frozen_key(url, baseline, candidate, path)
    return {
        "transition_id": _frozen_tid(url, baseline, candidate, path),
        "discovered_by": [{"query_id": "q1", "candidate_path": ".claude/settings.json"}],
        "repository_full_name": repo,
        "repository_url": url,
        "path": path,
        "baseline_commit": baseline,
        "candidate_commit": candidate,
        "baseline_blob": "c" * 40,
        "candidate_blob": "d" * 40,
        "baseline_sha256": "e" * 64,
        "candidate_sha256": "f" * 64,
        "baseline_size_bytes": 100,
        "candidate_size_bytes": 120,
        "candidate_commit_timestamp": "2026-09-01T00:00:00Z",
        "candidate_parent_count": 1,
        "permissions_changed": True,
        "screening_status": "pending",
        "exclusion_reasons": [],
        "contamination_status": "clean",
        "selection_key": key,
        "manual_review_required": True,
    }


def _make_chain(count: int = 12) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    """Build a valid synthetic raw+decisions pair with distinct repos."""
    contract, contract_bytes = _load_contract()
    transitions = []
    for index in range(count):
        repo = f"org/b1-chain-{index:03d}"
        baseline = f"{index + 7000:040x}"
        candidate = f"{index + 9000:040x}"
        path = _ALLOWED_PATHS[index % 2]
        transitions.append(
            _make_transition(repo=repo, baseline=baseline, candidate=candidate, path=path)
        )
    raw = {
        "schema_version": "permitdiff.dev/r3-public-discovery-ledger/v2",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "cb01_contract_version": "r3-cb01-corpus-construction-v1",
        "cb01_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "study_repository_commit": _VALID_STUDY,
        "producer_id": "permitdiff-r3-canonical-public-discovery-v2",
        "source": "github-rest-code-search-and-commit-history",
        "generated_at": "2026-09-01T00:00:00Z",
        "discovery_complete": True,
        "limitations": ["b1 synthetic fixture"],
        "queries": _queries_from_contract(contract),
        "discovered_location_count": 1,
        "transition_count": len(transitions),
        "transitions": copy.deepcopy(transitions),
    }
    raw_bytes = _canonical_bytes(raw)
    decisions_list = []
    for item in transitions:
        decisions_list.append(
            {
                "transition_id": item["transition_id"],
                "repository_url": item["repository_url"],
                "path": item["path"],
                "baseline_commit": item["baseline_commit"],
                "candidate_commit": item["candidate_commit"],
                "permissions_changed": item["permissions_changed"],
                "contamination_status": item["contamination_status"],
                "decision": "eligible",
                "exclusion_reasons": [],
                "rationale": _RATIONALE,
                "reviewer": _REVIEWER,
            }
        )
    decisions = {
        "schema_version": "permitdiff.dev/r3-screening-decisions/v1",
        "plan_version": "r3-exploratory-corpus-plan-v1",
        "protocol_version": "r3-benchmark-protocol-v1",
        "source_ledger_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "generated_at": "2026-09-02T00:00:00Z",
        "instructions": _INSTRUCTIONS,
        "decisions": decisions_list,
    }
    decisions_bytes = _canonical_bytes(decisions)
    return raw, raw_bytes, decisions, decisions_bytes


def _write_chain(tmp_path: Path) -> dict[str, Path]:
    """Materialize a valid synthetic chain under tmp_path only."""
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes = _make_chain()
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    screened_bytes = _canonical_bytes(screened)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection_bytes = _canonical_bytes(selection)
    paths = {
        "raw": tmp_path / "raw.json",
        "decisions": tmp_path / "decisions.json",
        "screened": tmp_path / "screened.json",
        "selection": tmp_path / "selection.json",
        "contract": tmp_path / "contract.json",
        "output": tmp_path / "lineage.json",
    }
    paths["raw"].write_bytes(raw_bytes)
    paths["decisions"].write_bytes(decisions_bytes)
    paths["screened"].write_bytes(screened_bytes)
    paths["selection"].write_bytes(selection_bytes)
    paths["contract"].write_bytes(contract_bytes)
    return paths


def _import_lines(path: Path) -> list[str]:
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("import ", "from "))
    ]


# ---------------------------------------------------------------------------
# B0 guardrails
# ---------------------------------------------------------------------------


def test_b0_no_network_imports_in_cb01_tooling() -> None:
    for path in (CB01_MODULE_PATH, LINEAGE_CLI_PATH):
        joined = "\n".join(_import_lines(path))
        for forbidden in ("urllib", "http.client", "socket", "requests", "urlopen"):
            assert forbidden not in joined, f"{path.name} imports {forbidden}"
        assert "GitHubClient" not in joined, f"{path.name} references GitHubClient"
        assert "permitdiff" not in joined.replace("permitdiff.dev", ""), (
            f"{path.name} imports PermitDiff runtime"
        )


def test_b0_thin_cli_has_no_duplicate_semantics() -> None:
    text = LINEAGE_CLI_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "selection_key_for",
        "transition_id_for",
        "contamination_status_for",
        "FIXED_EXCLUSION_REASONS",
        "CANDIDATE_PATHS",
        "derive_screened_ledger",
        "derive_selection_v2",
        "Draft202012Validator",
        "jsonschema",
    ):
        assert forbidden not in text, f"thin CLI duplicates {forbidden}"
    assert "derive_lineage_v1" in text


def test_b0_no_real_evidence_under_exploratory() -> None:
    names = {p.name for p in EXPLORATORY_DIR.iterdir()}
    assert names == _ALLOWLISTED_EXPLORATORY, f"unexpected exploratory files: {sorted(names)}"
    forbidden_patterns = (
        "discovery-ledger.json",
        "screening-decisions.json",
        "screened-discovery-ledger.json",
        "public-selection.json",
        "construction-lineage",
        "materialization.json",
        "public-historical",
    )
    for pattern in forbidden_patterns:
        assert list(EXPLORATORY_DIR.rglob(f"*{pattern}*")) == [], pattern


def test_b0_v1_ledger_rejected_by_cb01() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, _, _ = _make_chain(count=1)
    raw["schema_version"] = "permitdiff.dev/r3-discovery-ledger/v1"
    raw_bytes = _canonical_bytes(raw)
    with pytest.raises(CB01ConstructionError, match=r"unsupported raw discovery"):
        cb01.validate_raw_ledger(raw, raw_bytes, contract, contract_bytes)


def test_b0_v1_selection_rejected_by_cb01() -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes = _make_chain()
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    screened_bytes = _canonical_bytes(screened)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection["schema_version"] = "permitdiff.dev/r3-public-selection/v1"
    with pytest.raises(CB01ConstructionError, match=r"unsupported public selection"):
        cb01.validate_selection_v2(selection, contract, contract_bytes)


@pytest.mark.parametrize("field", ["target_cases", "eligible_case_count", "source_ledger_sha256"])
def test_b0_legacy_fields_fail_where_v2_expected(field: str) -> None:
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes = _make_chain()
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    screened_bytes = _canonical_bytes(screened)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection[field] = 1 if field != "source_ledger_sha256" else "a" * 64
    if field == "eligible_case_count":
        with pytest.raises(CB01ConstructionError, match=r"legacy"):
            cb01.validate_selection_v2(selection, contract, contract_bytes)
    # Legacy / v1 shapes must fail lineage construction end to end
    # (extra fields break deterministic equality with the derived v2 payload).
    selection_bytes = _canonical_bytes(selection)
    with pytest.raises(CB01ConstructionError):
        cb01.derive_lineage_v1(
            raw,
            raw_bytes,
            decisions,
            decisions_bytes,
            screened,
            screened_bytes,
            selection,
            selection_bytes,
            contract,
            contract_bytes,
        )


def test_b0_producers_not_yet_migrated() -> None:
    """Document B0+B1 scope: operational producers still emit v1 shapes."""
    import scripts.discover_r3_benchmark_candidates as discover
    import scripts.materialize_r3_public_selection as materialize
    import scripts.screen_r3_public_benchmark_candidates as screen

    assert discover.LEDGER_SCHEMA_VERSION == "permitdiff.dev/r3-discovery-ledger/v1"
    assert discover.SELECTION_SCHEMA_VERSION == "permitdiff.dev/r3-public-selection/v1"
    assert screen.SCREENING_SCHEMA_VERSION == "permitdiff.dev/r3-screening-decisions/v1"
    assert (
        materialize.MATERIALIZATION_SCHEMA_VERSION
        == "permitdiff.dev/r3-public-materialization/v1"
    )


# ---------------------------------------------------------------------------
# B1 CLI tests
# ---------------------------------------------------------------------------


def test_b1_valid_chain_builds_lineage(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    lineage = build_lineage(
        raw_path=paths["raw"],
        decisions_path=paths["decisions"],
        screened_path=paths["screened"],
        selection_path=paths["selection"],
        contract_path=paths["contract"],
        output_path=paths["output"],
    )
    assert paths["output"].exists()
    assert json.loads(paths["output"].read_bytes()) == lineage
    assert lineage["schema_version"] == "permitdiff.dev/r3-cb01-corpus-construction-lineage/v1"
    assert lineage["raw_discovery_ledger_sha256"] == hashlib.sha256(
        paths["raw"].read_bytes()
    ).hexdigest()
    assert lineage["screening_decisions_sha256"] == hashlib.sha256(
        paths["decisions"].read_bytes()
    ).hexdigest()


def test_b1_main_success_and_help(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    assert (
        main(
            [
                "--raw-ledger",
                str(paths["raw"]),
                "--screening-decisions",
                str(paths["decisions"]),
                "--screened-ledger",
                str(paths["screened"]),
                "--selection",
                str(paths["selection"]),
                "--contract",
                str(paths["contract"]),
                "--output",
                str(paths["output"]),
            ]
        )
        == 0
    )
    assert paths["output"].exists()
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_b1_parent_byte_mutation_fails(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    raw_bytes = paths["raw"].read_bytes()
    mutated = json.loads(raw_bytes)
    mutated["discovered_location_count"] = 9999
    paths["raw"].write_bytes(_canonical_bytes(mutated))
    assert (
        main(
            [
                "--raw-ledger",
                str(paths["raw"]),
                "--screening-decisions",
                str(paths["decisions"]),
                "--screened-ledger",
                str(paths["screened"]),
                "--selection",
                str(paths["selection"]),
                "--contract",
                str(paths["contract"]),
                "--output",
                str(paths["output"]),
            ]
        )
        != 0
    )
    assert not paths["output"].exists()


def test_b1_fabricated_screened_fails(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    screened = json.loads(paths["screened"].read_bytes())
    screened["transitions"][0]["screening_status"] = "excluded"
    screened["transitions"][0]["exclusion_reasons"] = ["insufficient_public_semantics"]
    paths["screened"].write_bytes(_canonical_bytes(screened))
    with pytest.raises(CB01ConstructionError):
        build_lineage(
            raw_path=paths["raw"],
            decisions_path=paths["decisions"],
            screened_path=paths["screened"],
            selection_path=paths["selection"],
            contract_path=paths["contract"],
            output_path=paths["output"],
        )
    assert not paths["output"].exists()


def test_b1_fabricated_selection_fails(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    selection = json.loads(paths["selection"].read_bytes())
    selection["shortfall"] = 999
    paths["selection"].write_bytes(_canonical_bytes(selection))
    with pytest.raises(CB01ConstructionError):
        build_lineage(
            raw_path=paths["raw"],
            decisions_path=paths["decisions"],
            screened_path=paths["screened"],
            selection_path=paths["selection"],
            contract_path=paths["contract"],
            output_path=paths["output"],
        )
    assert not paths["output"].exists()


def test_b1_no_generated_at_and_no_partial_output(tmp_path: Path) -> None:
    paths = _write_chain(tmp_path)
    lineage = build_lineage(
        raw_path=paths["raw"],
        decisions_path=paths["decisions"],
        screened_path=paths["screened"],
        selection_path=paths["selection"],
        contract_path=paths["contract"],
        output_path=paths["output"],
    )
    assert "generated_at" not in lineage
    assert "generated_at" not in json.loads(paths["output"].read_bytes())
    # Failure path leaves no partial file.
    output2 = tmp_path / "lineage-fail.json"
    assert (
        main(
            [
                "--raw-ledger",
                str(tmp_path / "missing.json"),
                "--screening-decisions",
                str(paths["decisions"]),
                "--screened-ledger",
                str(paths["screened"]),
                "--selection",
                str(paths["selection"]),
                "--contract",
                str(paths["contract"]),
                "--output",
                str(output2),
            ]
        )
        != 0
    )
    assert not output2.exists()
