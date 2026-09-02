"""Finalize reproducible CycloneDX SBOMs for GitHub attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

_REPOSITORY_URL = "https://github.com/TensorScholar/permitdiff"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bom_digest(sbom: dict[str, Any]) -> str:
    canonical_sbom = dict(sbom)
    canonical_sbom.pop("serialNumber", None)
    payload = json.dumps(
        canonical_sbom,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def finalize_cyclonedx_sbom(sbom_path: Path, subject_path: Path) -> str:
    """Add a deterministic CycloneDX serial number bound to BOM and subject content."""

    raw_sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    if not isinstance(raw_sbom, dict):
        raise ValueError("CycloneDX SBOM must contain a JSON object")
    if raw_sbom.get("bomFormat") != "CycloneDX":
        raise ValueError("SBOM bomFormat must be 'CycloneDX'")
    if not isinstance(raw_sbom.get("specVersion"), str):
        raise ValueError("CycloneDX SBOM must contain a string specVersion")

    subject_digest = _sha256_file(subject_path)
    bom_digest = _canonical_bom_digest(raw_sbom)
    identity = f"{_REPOSITORY_URL}/sbom/sha256/{subject_digest}/bom/{bom_digest}"
    serial_number = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, identity)}"

    raw_sbom["serialNumber"] = serial_number
    sbom_path.write_text(
        json.dumps(raw_sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return serial_number


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--subject", required=True, type=Path)
    args = parser.parse_args()

    try:
        serial_number = finalize_cyclonedx_sbom(args.sbom, args.subject)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"finalized CycloneDX SBOM with deterministic serialNumber {serial_number}")


if __name__ == "__main__":
    main()
