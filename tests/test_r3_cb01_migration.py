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
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.discover_r3_benchmark_candidates as _discover
import scripts.r3_cb01_corpus_construction as cb01
from scripts.build_r3_cb01_lineage import build_lineage, main
from scripts.discover_r3_benchmark_candidates import DiscoveryError
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
    """Document B0+B1 scope: operational producers still emit v1 shapes.

    Updated in B2: raw discovery now emits v2 while v1 selection is
    retained until B4 (known intermediate incompatibility, fail-closed).
    """
    import scripts.discover_r3_benchmark_candidates as discover
    import scripts.materialize_r3_public_selection as materialize
    import scripts.screen_r3_public_benchmark_candidates as screen

    assert discover.RAW_LEDGER_SCHEMA_VERSION == "permitdiff.dev/r3-public-discovery-ledger/v2"
    assert discover.LEDGER_SCHEMA_VERSION == "permitdiff.dev/r3-discovery-ledger/v1"
    assert discover.SELECTION_SCHEMA_VERSION == "permitdiff.dev/r3-public-selection/v1"
    assert screen.SCREENING_SCHEMA_VERSION == "permitdiff.dev/r3-screening-decisions/v1"
    # B5: materialization index is v2 (lineage-gated); the v1 index constant
    # is retained for downstream CB-02+ readers until their own migration.
    # Selection v1 consts above are retained history for the deprecated shape.
    assert (
        materialize.MATERIALIZATION_V2_SCHEMA_VERSION
        == "permitdiff.dev/r3-public-materialization/v2"
    )
    assert (
        materialize.MATERIALIZATION_SCHEMA_VERSION
        == "permitdiff.dev/r3-public-materialization/v1"
    )
    assert (
        materialize.SELECTION_SCHEMA_VERSION
        == "permitdiff.dev/r3-public-selection/v2"
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


# ---------------------------------------------------------------------------
# B2 — Raw discovery ledger v2 migration (synthetic, no network/tokens)
# ---------------------------------------------------------------------------

_B2_STUDY = "1" * 40
_B2_V2_SCHEMA_PATH = ROOT / "docs" / "r3-public-discovery-ledger-v2.schema.json"


class _FakeDiscoveryClient:
    """Minimal mocked GitHub client: search/history/commit/file only, no network."""

    def __init__(self) -> None:
        self.search_payloads: dict[str, tuple[list[dict[str, Any]], int, bool]] = {}
        self.histories: dict[tuple[str, str], tuple[list[dict[str, Any]], bool]] = {}
        self.commits: dict[tuple[str, str], dict[str, Any]] = {}
        self.files: dict[tuple[str, str, str], tuple[dict[str, Any], bytes]] = {}

    def search_code(self, query: str) -> tuple[list[dict[str, Any]], int, bool]:
        return self.search_payloads.get(query, ([], 0, False))

    def list_path_commits(
        self, repository: str, path: str, *, max_commits: int | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        commits, truncated = self.histories[(repository, path)]
        if max_commits is not None and len(commits) > max_commits:
            return commits[:max_commits], True
        return commits, truncated

    def get_commit(self, repository: str, commit: str) -> dict[str, Any]:
        return self.commits[(repository, commit)]

    def get_file(self, repository: str, path: str, ref: str) -> tuple[dict[str, Any], bytes]:
        return self.files[(repository, path, ref)]


def _b2_commit(sha: str) -> dict[str, Any]:
    return {"sha": sha, "commit": {"committer": {"date": "2026-01-02T00:00:00Z"}}}


def _b2_file(blob: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    raw = json.dumps(payload, sort_keys=True).encode()
    return ({"sha": blob, "type": "file", "encoding": "base64"}, raw)


def _b2_seeded_client() -> _FakeDiscoveryClient:
    """Seed one public location with one adjacent transition (no network)."""
    from scripts.discover_r3_benchmark_candidates import build_search_specs

    client = _FakeDiscoveryClient()
    specs = build_search_specs()
    repo = "org/b2-public"
    path = ".claude/settings.json"
    baseline = "b" * 40
    candidate = "c" * 40
    client.search_payloads[specs[0].api_query] = (
        [
            {
                "path": path,
                "sha": "a" * 40,
                "html_url": f"https://github.com/{repo}/blob/main/{path}",
                "repository": {"full_name": repo},
            }
        ],
        1,
        False,
    )
    client.histories[(repo, path)] = (
        [_b2_commit(candidate), _b2_commit(baseline)],
        False,
    )
    client.commits[(repo, candidate)] = {"parents": [{"sha": baseline}]}
    client.files[(repo, path, baseline)] = _b2_file("1" * 40, {"permissions": {"allow": []}})
    client.files[(repo, path, candidate)] = _b2_file(
        "2" * 40, {"permissions": {"allow": ["Bash"]}}
    )
    return client


def _b2_build_valid() -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    contract, contract_bytes = _load_contract()
    ledger = _discover.build_ledger(
        _b2_seeded_client(), contract, contract_bytes, _B2_STUDY
    )
    ledger_bytes = _canonical_bytes(ledger)
    return ledger, ledger_bytes, contract, contract_bytes


def test_b2_valid_mocked_discovery_produces_raw_v2() -> None:
    from jsonschema import Draft202012Validator

    ledger, ledger_bytes, contract, contract_bytes = _b2_build_valid()
    assert ledger["schema_version"] == "permitdiff.dev/r3-public-discovery-ledger/v2"
    assert ledger["producer_id"] == "permitdiff-r3-canonical-public-discovery-v2"
    assert ledger["cb01_contract_version"] == "r3-cb01-corpus-construction-v1"
    assert ledger["cb01_contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    assert ledger["study_repository_commit"] == _B2_STUDY
    assert ledger["transition_count"] == 1
    schema = json.loads(_B2_V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(ledger)
    cb01.validate_raw_ledger(ledger, ledger_bytes, contract, contract_bytes)


def test_b2_contract_binding_exact_bytes() -> None:
    contract, contract_bytes = _load_contract()
    ledger, _, _, _ = _b2_build_valid()
    assert ledger["cb01_contract_sha256"] == hashlib.sha256(contract_bytes).hexdigest()
    # Same semantics, different whitespace => different digest (exact bytes matter).
    reformatted = (
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    assert json.loads(reformatted) == contract
    assert hashlib.sha256(reformatted).hexdigest() != ledger["cb01_contract_sha256"]
    # Mismatched dict/bytes pair fails closed.
    tampered_bytes = bytearray(contract_bytes)
    tampered_bytes[-2] = ord("X") if tampered_bytes[-2] != ord("X") else ord("Y")
    with pytest.raises(DiscoveryError, match=r"invalid CB-01 contract"):
        _discover.build_ledger(
            _b2_seeded_client(), contract, bytes(tampered_bytes), _B2_STUDY
        )


def test_b2_study_commit_clean_and_dirty(monkeypatch: Any, tmp_path: Path) -> None:
    contract, contract_bytes = _load_contract()
    # Invalid study commits fail closed without touching git.
    for bad in ("A" * 40, "a" * 39, "", "zz" + "a" * 38):
        with pytest.raises(DiscoveryError, match=r"study repository commit"):
            _discover.build_ledger(
                _b2_seeded_client(), contract, contract_bytes, bad
            )
    # Fake git states: clean accepted, dirty/missing rejected (no real git).

    def _clean(cmd: Any, **kwargs: Any) -> str:
        assert cmd[0].endswith("git")
        if cmd[1:3] == ["rev-parse", "HEAD"]:
            return _B2_STUDY + "\n"
        return ""

    monkeypatch.setattr(subprocess, "check_output", _clean)
    assert _discover._study_repository_commit(tmp_path) == _B2_STUDY

    def _dirty(cmd: Any, **kwargs: Any) -> str:
        if cmd[1:3] == ["rev-parse", "HEAD"]:
            return _B2_STUDY + "\n"
        return " M some/file.py\n"

    monkeypatch.setattr(subprocess, "check_output", _dirty)
    with pytest.raises(DiscoveryError, match=r"dirty"):
        _discover._study_repository_commit(tmp_path)

    def _missing(cmd: Any, **kwargs: Any) -> str:
        raise FileNotFoundError("no git")

    monkeypatch.setattr(subprocess, "check_output", _missing)
    with pytest.raises(DiscoveryError, match=r"cannot record"):
        _discover._study_repository_commit(tmp_path)


def test_b2_producer_identity_required() -> None:
    ledger, _, contract, contract_bytes = _b2_build_valid()
    assert ledger["producer_id"] == "permitdiff-r3-canonical-public-discovery-v2"
    tampered = copy.deepcopy(ledger)
    tampered["producer_id"] = "legacy-producer"
    with pytest.raises(CB01ConstructionError, match=r"producer_id"):
        cb01.validate_raw_ledger(
            tampered, _canonical_bytes(tampered), contract, contract_bytes
        )


def test_b2_identity_formulas_match_cb01_and_register() -> None:
    contract, _contract_bytes = _load_contract()
    ledger, _, _, _ = _b2_build_valid()
    item = ledger["transitions"][0]
    url = item["repository_url"]
    baseline = item["baseline_commit"]
    candidate = item["candidate_commit"]
    path = item["path"]
    expected_key = hashlib.sha256(
        f"{url}\n{baseline}\n{candidate}\n{path}".encode()
    ).hexdigest()
    assert item["selection_key"] == expected_key
    assert item["transition_id"] == "gh-" + expected_key[:20]
    assert item["repository_url"] == f"https://github.com/{item['repository_full_name']}"
    # Contamination comes from the frozen contract register.
    entry = contract["contamination_register"][0]
    assert _discover._control_status(
        entry["repository_url"],
        entry["baseline_commit"],
        entry["candidate_commit"],
        entry["path"],
        contract,
    ) == "pre_exposed_engineering_control"
    assert (
        _discover._control_status(url, baseline, candidate, path, contract) == "clean"
    )
    assert item["contamination_status"] == "clean"


def test_b2_regression_transition_identities_stable() -> None:
    from scripts.discover_r3_benchmark_candidates import build_search_specs

    ledger, _, contract, _ = _b2_build_valid()
    item = ledger["transitions"][0]
    assert (
        item["repository_full_name"],
        item["baseline_commit"],
        item["candidate_commit"],
        item["path"],
    ) == ("org/b2-public", "b" * 40, "c" * 40, ".claude/settings.json")
    # Query strings, ordering, and paths unchanged; match frozen contract frame.
    specs = build_search_specs()
    assert len(specs) == 10
    frame = {
        (e["query_id"], e["candidate_path"]): e["api_query"]
        for e in contract["search_frame"]
    }
    for spec in specs:
        assert spec.api_query == frame[(spec.query_id, spec.path)]
    assert _discover.CANDIDATE_PATHS == _discover._cb01.CANDIDATE_PATHS
    assert _discover.FIXED_EXCLUSION_REASONS == _discover._cb01.FIXED_EXCLUSION_REASONS


def test_b2_no_network_in_discovery_migration() -> None:
    text = (
        ROOT / "scripts" / "discover_r3_benchmark_candidates.py"
    ).read_text(encoding="utf-8")
    assert "import requests" not in text
    assert "import socket" not in text or "ssl.SSLEOFError" in text
    public_text = (
        ROOT / "scripts" / "discover_r3_public_benchmark_candidates.py"
    ).read_text(encoding="utf-8")
    assert "import requests" not in public_text
    # New helpers perform file + git reads only (subprocess git is allowed in
    # scripts per ruff per-file-ignores S603); migration tests never resolve
    # real GitHub tokens (split literals avoid self-matching this guard).
    own_text = Path(__file__).read_text(encoding="utf-8")
    assert ("GH_" + "TOKEN") not in own_text.replace('"' + "GH_" + 'TOKEN"', "")
    assert ("monkeypatch." + "setenv") not in own_text


# ---------------------------------------------------------------------------
# B4 — Selection v2 via CB-01 (synthetic, no network/tokens/discovery)
# ---------------------------------------------------------------------------


def _b4_screened(
    count: int, *, repos: list[str] | None = None
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    """Build a valid screened v1 ledger via CB01 derivation (synthetic)."""
    contract, contract_bytes = _load_contract()
    transitions: list[dict[str, Any]] = []
    for index in range(count):
        repo = repos[index % len(repos)] if repos else f"org/b4-sel-{index:03d}"
        path = _ALLOWED_PATHS[index % 2]
        url = _frozen_url(repo)
        baseline = f"{index + 3000:040x}"
        candidate = f"{index + 8000:040x}"
        key = _frozen_key(url, baseline, candidate, path)
        transitions.append(
            {
                "transition_id": _frozen_tid(url, baseline, candidate, path),
                "discovered_by": [{"query_id": "q1", "candidate_path": path}],
                "repository_full_name": repo,
                "repository_url": url,
                "path": path,
                "baseline_commit": baseline,
                "candidate_commit": candidate,
                "baseline_blob": f"{index + 110:040x}",
                "candidate_blob": f"{index + 210:040x}",
                "baseline_sha256": f"{index + 310:064x}",
                "candidate_sha256": f"{index + 410:064x}",
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
        "limitations": ["b4 synthetic fixture"],
        "queries": _queries_from_contract(contract),
        "discovered_location_count": 1,
        "transition_count": len(transitions),
        "transitions": copy.deepcopy(transitions),
    }
    raw_bytes = _canonical_bytes(raw)
    decisions_list = [
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
        for item in transitions
    ]
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
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    return screened, _canonical_bytes(screened), contract, contract_bytes


def test_b4_producer_matches_cb01_derivation() -> None:
    screened, screened_bytes, contract, contract_bytes = _b4_screened(12)
    expected = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    produced = _discover.select_public_historical(
        screened, screened_bytes, contract, contract_bytes
    )
    assert produced == expected
    assert produced["schema_version"] == "permitdiff.dev/r3-public-selection/v2"
    assert produced["target_case_count"] == 18
    assert produced["raw_eligible_count"] == 12
    assert produced["selected_case_count"] == 12
    assert produced["shortfall"] == 6
    assert "target_cases" not in produced
    assert "eligible_case_count" not in produced
    assert "source_ledger_sha256" not in produced


def test_b4_exact_screened_byte_digest(tmp_path: Path) -> None:
    screened, screened_bytes, _, _ = _b4_screened(12)
    screened_path = tmp_path / "screened.json"
    screened_path.write_bytes(screened_bytes)
    output_path = tmp_path / "selection.json"
    assert (
        _discover.main(
            ["select", "--ledger", str(screened_path), "--output", str(output_path)]
        )
        == 0
    )
    output = json.loads(output_path.read_bytes())
    assert output["source_screened_ledger_sha256"] == hashlib.sha256(screened_bytes).hexdigest()
    # Same semantics, different whitespace => different digest, binding fails.
    reformatted = (
        json.dumps(screened, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    assert json.loads(reformatted) == screened
    assert hashlib.sha256(reformatted).hexdigest() != output["source_screened_ledger_sha256"]
    screened_path.write_bytes(reformatted)
    output2 = tmp_path / "selection2.json"
    assert (
        _discover.main(
            ["select", "--ledger", str(screened_path), "--output", str(output2)]
        )
        == 0
    )
    assert (
        json.loads(output2.read_bytes())["source_screened_ledger_sha256"]
        == hashlib.sha256(reformatted).hexdigest()
    )


def test_b4_public_cli_valid_selection(tmp_path: Path) -> None:
    import scripts.discover_r3_public_benchmark_candidates as _public

    _, screened_bytes, _, _ = _b4_screened(12)
    screened_path = tmp_path / "screened.json"
    screened_path.write_bytes(screened_bytes)
    output_path = tmp_path / "selection.json"
    assert (
        _public.main(
            ["select", "--ledger", str(screened_path), "--output", str(output_path)]
        )
        == 0
    )
    output = json.loads(output_path.read_bytes())
    assert output["schema_version"] == "permitdiff.dev/r3-public-selection/v2"
    assert output["selected_case_count"] == 12


@pytest.mark.parametrize("flag", ["--target", "--max-per-repository"])
def test_b4_cli_overrides_rejected_both_mains(tmp_path: Path, flag: str) -> None:
    import scripts.discover_r3_public_benchmark_candidates as _public

    _, screened_bytes, _, _ = _b4_screened(12)
    screened_path = tmp_path / "screened.json"
    screened_path.write_bytes(screened_bytes)
    value = "17" if flag == "--target" else "3"
    for entrypoint in (_discover.main, _public.main):
        output_path = tmp_path / f"out-{entrypoint.__module__}-{value}.json"
        assert (
            entrypoint(
                [
                    "select",
                    "--ledger",
                    str(screened_path),
                    "--output",
                    str(output_path),
                    flag,
                    value,
                ]
            )
            == 1
        )
        assert not output_path.exists()


def test_b4_below_minimum_no_output_both_mains(tmp_path: Path) -> None:
    import scripts.discover_r3_public_benchmark_candidates as _public

    _, screened_bytes, _, _ = _b4_screened(5)
    screened_path = tmp_path / "screened.json"
    screened_path.write_bytes(screened_bytes)
    for entrypoint in (_discover.main, _public.main):
        output_path = tmp_path / f"below-{entrypoint.__module__}.json"
        assert (
            entrypoint(
                ["select", "--ledger", str(screened_path), "--output", str(output_path)]
            )
            == 1
        )
        assert not output_path.exists()


# ---------------------------------------------------------------------------
# B5 — Lineage-gated materialization CLI (synthetic, no network/tokens)
#
# Failure paths exit non-zero with no output directory. Gate failures occur
# before any source fetch, so these CLI tests never touch the network even
# though main() constructs a real client object (no calls are made).
# ---------------------------------------------------------------------------


def _b5_cli_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Write a valid synthetic selection+lineage pair under tmp_path."""
    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes = _make_chain()
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    screened_bytes = _canonical_bytes(screened)
    selection = cb01.derive_selection_v2(screened, screened_bytes, contract, contract_bytes)
    selection_bytes = _canonical_bytes(selection)
    lineage = cb01.derive_lineage_v1(
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
    selection_path = tmp_path / "selection.json"
    lineage_path = tmp_path / "lineage.json"
    selection_path.write_bytes(selection_bytes)
    lineage_path.write_bytes(_canonical_bytes(lineage))
    return selection_path, lineage_path, CONTRACT_PATH


def test_b5_cli_missing_lineage_no_output(tmp_path: Path) -> None:
    import scripts.materialize_r3_public_selection as _materialize

    selection_path, _, _ = _b5_cli_pair(tmp_path)
    output_dir = tmp_path / "materialized"
    assert (
        _materialize.main(
            [
                "--selection",
                str(selection_path),
                "--lineage",
                str(tmp_path / "missing-lineage.json"),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )
    assert not output_dir.exists()


def test_b5_cli_tampered_lineage_no_output(tmp_path: Path) -> None:
    import scripts.materialize_r3_public_selection as _materialize

    selection_path, lineage_path, _ = _b5_cli_pair(tmp_path)
    lineage = json.loads(lineage_path.read_bytes())
    lineage["public_selection_sha256"] = "0" * 64
    lineage_path.write_bytes(_canonical_bytes(lineage))
    output_dir = tmp_path / "materialized"
    assert (
        _materialize.main(
            [
                "--selection",
                str(selection_path),
                "--lineage",
                str(lineage_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )
    assert not output_dir.exists()


def test_b5_cli_below_minimum_no_output(tmp_path: Path) -> None:
    import scripts.materialize_r3_public_selection as _materialize

    contract, contract_bytes = _load_contract()
    raw, raw_bytes, decisions, decisions_bytes = _make_chain(count=5)
    screened = cb01.derive_screened_ledger(
        raw, raw_bytes, decisions, decisions_bytes, contract, contract_bytes
    )
    assert len([t for t in screened["transitions"] if t["screening_status"] == "eligible"]) == 5
    # Below-minimum selections cannot exist canonically; emulate a truncated
    # payload to prove the gate refuses before any fetch.
    selection_path, lineage_path, _ = _b5_cli_pair(tmp_path)
    selection = json.loads(selection_path.read_bytes())
    selection["selected"] = selection["selected"][:5]
    selection["selected_case_count"] = 5
    selection["shortfall"] = 13
    selection_path.write_bytes(_canonical_bytes(selection))
    output_dir = tmp_path / "materialized"
    assert (
        _materialize.main(
            [
                "--selection",
                str(selection_path),
                "--lineage",
                str(lineage_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 1
    )
    assert not output_dir.exists()
