# Exploratory corpus

This directory is intentionally mutable, but corpus construction is governed by the preregistered methodology in `docs/r3-exploratory-corpus-plan.md` and its machine-readable companion `selection-plan.json`.

Use this area for source discovery ledgers, immutable public historical review units, synthetic coverage cases, unsupported/unknown stress cases, blinded review packets, adjudication records, manifests, and integrity evidence.

Exploratory outcomes are not confirmatory product evidence and must not be used to upgrade PermitDiff beyond `ENGINEERING VERIFIED`.

## Pre-execution rule

Do not run PermitDiff against newly selected exploratory cases until the preregistered discovery ledger, deterministic selected-case list, source artifacts/provenance, provisional adjudications, canonical manifest, and integrity-validator evidence are committed.

Any corpus or label change after first product execution must create a new exploratory corpus version rather than silently replacing the prior state.

## Example manifest

`manifest.example.json` is a structurally representative example only. Its placeholder digests and reviewer metadata are not evidence and it is not part of the real exploratory corpus.

## Known pre-exposed control

The `SpearIT-LLC/project-framework` transition already used by the external-repository validation workflow is registered as a pre-exposed engineering control and is excluded from the unbiased public historical selection slice.
