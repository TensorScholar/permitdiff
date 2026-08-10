"""Regression tests for the Docker reproducibility contract (B1-F08).

Static checks prove the container contract invariants (pinned base digest,
PEP 427 wheel handoff, hash-checked installs, no unhashed network resolution,
generative refresh path, supported-platform policy) and unit tests exercise the
refresh script's pure lock-merging logic. End-to-end behavioral validation
(no-cache builds, negative hash proofs) is documented in
docs/docker-reproducibility.md.
"""

from __future__ import annotations

import importlib.util
import os
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
RUNTIME_LOCK = ROOT / "docker" / "requirements.lock"
BUILD_TOOLS_LOCK = ROOT / "docker" / "build-requirements.lock"
REFRESH_SCRIPT = ROOT / "scripts" / "refresh_docker_lock.py"
DOCS = ROOT / "docs" / "docker-reproducibility.md"

# Verified immutable multi-architecture OCI index digest for python:3.13-slim
# (Python 3.13.14 slim-trixie). Refresh deliberately and only together with
# scripts/refresh_docker_lock.py: see docs/docker-reproducibility.md.
BASE_DIGEST = "sha256:9662417aace5ae7b8e2609cce472b72a8958e134ba372808abe9cc1a0c0125e6"
BASE_IMAGE = "python:3.13-slim"
BASE_REF = f"{BASE_IMAGE}@{BASE_DIGEST}"

_FROM_RE = re.compile(r"^FROM\s+(\S+)(?:\s+AS\s+(\S+))?$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA_RE = re.compile(r"sha256:[0-9a-f]{64}")
_PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ]+)(.*)$")

SHA_256 = "sha256:"


def _load_refresh_module() -> object:
    spec = importlib.util.spec_from_file_location("refresh_docker_lock", REFRESH_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flatten() -> list[str]:
    """Return logical Dockerfile lines with backslash continuations joined."""
    lines: list[str] = []
    current: list[str] = []
    for raw in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = raw.rstrip()
        if not stripped or stripped.startswith("#"):
            continue
        current.append(stripped[:-1] if stripped.endswith("\\") else stripped)
        if not stripped.endswith("\\"):
            lines.append(" ".join(current))
            current = []
    if current:
        lines.append(" ".join(current))
    return lines


def _stage_blocks() -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    stage: str | None = None
    for line in _flatten():
        match = _FROM_RE.match(line)
        if match:
            stage = match.group(2) or "runtime"
            blocks.setdefault(stage, []).append(line)
        elif stage is not None:
            blocks[stage].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def _parse_lock(path: Path) -> dict[str, tuple[str, set[str]]]:
    pins: dict[str, tuple[str, set[str]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _PIN_RE.fullmatch(line.strip())
        assert match is not None, f"malformed lock line: {line!r}"
        name, version, rest = match.groups()
        hashes = set(_SHA_RE.findall(rest))
        assert hashes, f"lock line without a SHA-256 hash: {line!r}"
        assert all(len(h.split(":")[1]) == 64 for h in hashes), f"bad hash in: {line!r}"
        pins[canonicalize_name(name)] = (version, hashes)
    return pins


def test_dockerfile_pins_base_image_by_immutable_digest() -> None:
    images = [match.group(1) for line in _flatten() if (match := _FROM_RE.match(line))]
    assert len(images) == 3, f"expected resolve/build/runtime stages, found {images}"
    assert _DIGEST_RE.fullmatch(BASE_DIGEST)
    for image in images:
        assert image == BASE_REF, f"unpinned or stale base image reference: {image!r}"


def test_dockerfile_keeps_valid_wheel_filename() -> None:
    # The invalid rename appears in the Dockerfile as a comment example only;
    # static scan of the repo-supplied Dockerfile, not a real temp-file use.
    invalid_rename = "/tmp/permitdiff.whl"  # noqa: S108
    lines = _flatten()
    assert "COPY --from=build /build/dist/*.whl /tmp/dist/" in lines
    assert all(not line.startswith("COPY") or invalid_rename not in line for line in lines)


def test_runtime_dependencies_installed_with_hashed_lock() -> None:
    stage = _stage_blocks()["runtime"]
    assert "--only-binary=:all:" in stage
    assert "--require-hashes" in stage
    assert "-r /tmp/docker/requirements.lock" in stage
    assert "pip install --no-cache-dir --no-deps /tmp/dist/*.whl" in stage
    assert "pip check" in stage


def test_build_tooling_installed_with_hashed_lock() -> None:
    stage = _stage_blocks()["build"]
    assert "--only-binary=:all:" in stage
    assert "--require-hashes" in stage
    assert "-r docker/build-requirements.lock" in stage
    assert "python -m build --wheel --no-isolation" in stage


def test_every_pip_install_is_hash_checked_or_local() -> None:
    for _name, stage in _stage_blocks().items():
        for line in stage.splitlines():
            if "pip install" not in line:
                continue
            assert "--require-hashes" in line or "--no-deps" in line, (
                f"unconstrained install: {line}"
            )
            if "--require-hashes" in line:
                assert "--only-binary=:all:" in line


def test_resolve_stage_materializes_declarations_without_installing() -> None:
    resolve = _stage_blocks()["resolve"]
    assert "python emit_project_dependencies.py > deps.txt" in resolve
    assert "pip install" not in resolve
    assert "pip download" not in resolve


def test_runtime_lock_is_exact_and_hashed() -> None:
    pins = _parse_lock(RUNTIME_LOCK)
    assert pins
    for _name, (version, hashes) in pins.items():
        assert re.fullmatch(r"[0-9][0-9A-Za-z.+\-!]*", version), version
        assert hashes
    # Binary wheels carry one hash per supported platform.
    assert len(pins["pydantic-core"][1]) >= 2
    assert len(pins["pyyaml"][1]) >= 2


def test_build_tool_lock_is_exact_and_hashed() -> None:
    pins = _parse_lock(BUILD_TOOLS_LOCK)
    refresh = _load_refresh_module()
    assert {name: pins[name][0] for name in sorted(pins)} == dict(
        sorted(refresh.BUILD_TOOL_PINS.items())
    )
    assert all(hashes for _version, hashes in pins.values())


def test_pyproject_build_system_keeps_public_range() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requires = pyproject["build-system"]["requires"]
    assert "setuptools>=77" in requires
    assert not any("==" in item for item in requires)


def test_runtime_lock_covers_declared_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pins = _parse_lock(RUNTIME_LOCK)
    for raw in pyproject["project"]["dependencies"]:
        requirement = Requirement(raw)
        name = canonicalize_name(requirement.name)
        assert name in pins, f"no lock pin for declared dependency {name}"
        version = pins[name][0]
        assert requirement.specifier.contains(version, prereleases=True), (
            f"{name} pinned to {version}, which violates {requirement.specifier}"
        )


def test_runtime_lock_does_not_pin_the_application_itself() -> None:
    pins = _parse_lock(RUNTIME_LOCK)
    assert "permitdiff" not in pins


def test_resolve_stage_is_independent_of_committed_locks() -> None:
    blocks = _stage_blocks()
    assert "resolve" in blocks, f"no resolve stage; stages: {sorted(blocks)}"
    resolve = blocks["resolve"]
    assert "COPY pyproject.toml" in resolve
    assert "emit_project_dependencies.py" in resolve
    assert "requirements.lock" not in resolve


def test_refresh_script_supported_platform_policy() -> None:
    refresh = _load_refresh_module()
    assert refresh.SUPPORTED_PLATFORMS == ("linux/amd64", "linux/arm64")


def test_refresh_script_merges_hashes_across_platforms() -> None:
    refresh = _load_refresh_module()
    merged = refresh.merge_records(
        [
            {"alpha": {"1.0": {"a" * 64, "b" * 64}}, "beta": {"2.0": {"d" * 64}}},
            {"alpha": {"1.0": {"b" * 64, "c" * 64}}, "beta": {"2.0": {"d" * 64, "e" * 64}}},
        ]
    )
    lock = refresh.render_lock(merged, "# header\n")
    assert f"--hash={SHA_256}{'a' * 64}" in lock
    assert f"--hash={SHA_256}{'b' * 64}" in lock
    assert f"--hash={SHA_256}{'c' * 64}" in lock
    assert f"--hash={SHA_256}{'d' * 64}" in lock
    assert f"--hash={SHA_256}{'e' * 64}" in lock
    # Deterministic: names sorted, hashes sorted per line, header preserved.
    body = [line for line in lock.splitlines() if line and not line.startswith("#")]
    assert body[0].startswith("alpha==1.0 ")
    assert body[1].startswith("beta==2.0 ")
    assert lock.startswith("# header")


def test_refresh_script_rejects_platform_version_mismatch() -> None:
    refresh = _load_refresh_module()
    try:
        refresh.merge_records(
            [
                {"alpha": {"1.0": {SHA_256 + "a" * 64}}},
                {"alpha": {"2.0": {SHA_256 + "b" * 64}}},
            ]
        )
    except SystemExit as exc:
        assert "version mismatch for alpha" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected SystemExit for platform version mismatch")


def _assert_merge_rejects_missing_package(
    refresh: object, records: list[dict[str, object]], platform: str, name: str
) -> None:
    try:
        refresh.merge_records(
            records,
            platforms=("linux/amd64", "linux/arm64"),
        )
    except SystemExit as exc:
        message = str(exc)
        assert platform in message
        assert name in message
    else:  # pragma: no cover - defensive
        raise AssertionError(f"expected SystemExit for package missing on {platform}")


def test_refresh_script_rejects_package_missing_on_amd64() -> None:
    refresh = _load_refresh_module()
    _assert_merge_rejects_missing_package(
        refresh,
        [
            {"beta": {"2.0": {SHA_256 + "d" * 64}}},
            {"alpha": {"1.0": {SHA_256 + "a" * 64}}, "beta": {"2.0": {SHA_256 + "d" * 64}}},
        ],
        "linux/amd64",
        "alpha",
    )


def test_refresh_script_rejects_package_missing_on_arm64() -> None:
    refresh = _load_refresh_module()
    _assert_merge_rejects_missing_package(
        refresh,
        [
            {"alpha": {"1.0": {SHA_256 + "a" * 64}}, "beta": {"2.0": {SHA_256 + "d" * 64}}},
            {"alpha": {"1.0": {SHA_256 + "a" * 64}}},
        ],
        "linux/arm64",
        "beta",
    )


def test_refresh_script_rejects_platform_record_count_mismatch() -> None:
    refresh = _load_refresh_module()
    try:
        refresh.merge_records([{"alpha": {"1.0": {SHA_256 + "a" * 64}}}])
    except SystemExit as exc:
        assert "does not match platforms" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected SystemExit for record count mismatch")


def test_lock_artifacts_are_shipped_and_documented() -> None:
    assert RUNTIME_LOCK.is_file()
    assert BUILD_TOOLS_LOCK.is_file()
    assert DOCS.is_file()
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "docker/requirements.lock" in manifest
    assert "docker/build-requirements.lock" in manifest
    assert os.access(REFRESH_SCRIPT, os.X_OK)
    assert (ROOT / "scripts" / "emit_project_dependencies.py").is_file()


def test_supported_platforms_are_documented() -> None:
    text = DOCS.read_text(encoding="utf-8")
    assert "linux/amd64" in text
    assert "linux/arm64" in text
    assert "--require-hashes" in text
    assert "--only-binary=:all:" in text
