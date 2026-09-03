"""Read-only, provenance-bound policy loading from local Git object databases."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from permitdiff.errors import PolicyLoadError
from permitdiff.policy import PolicyDocument
from permitdiff.yaml_utils import safe_load_yaml

_MAX_POLICY_BYTES = 1_000_000
_MAX_GIT_PATH_LENGTH = 1024
_MAX_GIT_REF_LENGTH = 512
_OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_FORBIDDEN_REF_FRAGMENTS = ("..", "@{", "\\", ":", "?", "*", "[", "~", "^")


class GitPolicyEvidence(BaseModel):
    """Exact Git provenance for a policy loaded without checking out the baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["permitdiff.git-policy-source/v1alpha1"] = (
        "permitdiff.git-policy-source/v1alpha1"
    )
    requested_ref: str
    resolved_commit: str
    path: str
    git_object_id: str
    raw_sha256: str


class ResolvedGitPolicy(BaseModel):
    """Validated policy plus immutable source provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: PolicyDocument
    evidence: GitPolicyEvidence


def load_policy_from_git(
    ref: str,
    path: str | Path,
    *,
    repository: str | Path = ".",
) -> ResolvedGitPolicy:
    """Load a policy blob from an already-available Git ref without checkout or code execution."""

    requested_ref = _validate_ref(ref)
    git_path = _validate_git_path(path)
    repository_path = Path(repository).resolve()
    if not repository_path.is_dir():
        raise PolicyLoadError(f"Git repository path is not a directory: {repository_path}")

    resolved_commit = _git_text(
        repository_path,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{requested_ref}^{{commit}}",
    ).strip()
    _validate_oid(resolved_commit, "resolved commit")

    object_id = _git_text(
        repository_path,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{resolved_commit}:{git_path}",
    ).strip()
    _validate_oid(object_id, "policy object")

    object_type = _git_text(repository_path, "cat-file", "-t", object_id).strip()
    if object_type != "blob":
        raise PolicyLoadError(
            f"Git policy source {requested_ref}:{git_path} resolved to {object_type!r}, not a blob"
        )

    size_text = _git_text(repository_path, "cat-file", "-s", object_id).strip()
    try:
        size = int(size_text)
    except ValueError as exc:  # pragma: no cover - Git contract violation
        raise PolicyLoadError(f"Git returned invalid blob size {size_text!r}") from exc
    if size > _MAX_POLICY_BYTES:
        raise PolicyLoadError(f"policy exceeds {_MAX_POLICY_BYTES} bytes")

    payload = _git_bytes(repository_path, "cat-file", "blob", object_id)
    if len(payload) != size:
        raise PolicyLoadError(
            f"Git policy blob size changed while reading: expected {size}, received {len(payload)}"
        )

    try:
        text = payload.decode("utf-8")
        raw = safe_load_yaml(text)
        if not isinstance(raw, dict):
            raise TypeError("policy root must be a mapping")
        policy = PolicyDocument.model_validate(raw)
    except (UnicodeError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise PolicyLoadError(
            f"failed to load Git policy {resolved_commit}:{git_path}: {exc}"
        ) from exc

    evidence = GitPolicyEvidence(
        requested_ref=requested_ref,
        resolved_commit=resolved_commit,
        path=git_path,
        git_object_id=object_id,
        raw_sha256=hashlib.sha256(payload).hexdigest(),
    )
    return ResolvedGitPolicy(policy=policy, evidence=evidence)


def _validate_ref(value: str) -> str:
    ref = value.strip()
    if ref != value or not ref or len(ref) > _MAX_GIT_REF_LENGTH:
        raise PolicyLoadError("Git baseline ref must be non-empty, canonical, and at most 512 chars")
    if ref.startswith("-") or any(fragment in ref for fragment in _FORBIDDEN_REF_FRAGMENTS):
        raise PolicyLoadError(f"unsupported Git baseline ref syntax: {ref!r}")
    if any(character.isspace() or ord(character) < 32 for character in ref):
        raise PolicyLoadError(f"unsupported whitespace/control character in Git ref: {ref!r}")
    return ref


def _validate_git_path(value: str | Path) -> str:
    raw = str(value)
    if not raw or len(raw) > _MAX_GIT_PATH_LENGTH or "\0" in raw or "\\" in raw:
        raise PolicyLoadError("Git policy path must be a non-empty canonical POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PolicyLoadError(f"Git policy path must be relative and traversal-free: {raw!r}")
    normalized = path.as_posix()
    if normalized != raw or ":" in normalized:
        raise PolicyLoadError(f"Git policy path must use canonical POSIX syntax: {raw!r}")
    return normalized


def _validate_oid(value: str, label: str) -> None:
    if _OID_RE.fullmatch(value) is None:
        raise PolicyLoadError(f"Git returned invalid {label} object id: {value!r}")


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise PolicyLoadError("git executable is required for --baseline-ref")
    return str(Path(executable).resolve())


def _git_bytes(repository: Path, *args: str) -> bytes:
    # Git invocation is the feature boundary: argv is explicit, shell=False, and the executable
    # is resolved to an absolute path. S603 cannot distinguish this constrained subprocess use.
    result = subprocess.run(  # noqa: S603
        [_git_executable(), "-C", str(repository), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise PolicyLoadError(f"git {' '.join(args)} failed: {stderr or 'unknown Git error'}")
    return result.stdout


def _git_text(repository: Path, *args: str) -> str:
    try:
        return _git_bytes(repository, *args).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyLoadError(f"git {' '.join(args)} returned non-UTF-8 metadata") from exc
