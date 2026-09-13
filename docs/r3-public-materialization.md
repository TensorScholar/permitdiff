# R3 public artifact materialization

## Status

This document defines the artifact-vendoring step after output-blind screening and
deterministic Slice A selection. The tool retrieves only the exact baseline/candidate
states named by the frozen public selection. It does not execute PermitDiff or assign
security labels.

## Command

After a complete screened ledger has produced `public-selection.json`:

```bash
python scripts/materialize_r3_public_selection.py \
  --selection validation/r3-benchmark/exploratory/public-selection.json \
  --output-dir validation/r3-benchmark/exploratory/public-historical-v1
```

The command reads `GH_TOKEN` or `GITHUB_TOKEN` only as a GitHub API transport
credential. The token is never written to the materialization index or vendored
artifacts.

## Fail-closed public-source boundary

Before retrieving file bytes from each selected repository, the tool queries repository
metadata and requires GitHub to report both:

- `private == false`
- `full_name` exactly equal to the selected repository identity

A repository that became private or changed identity after selection is not silently
materialized through a credential that happens to retain access. The run fails and the
provenance problem must be handled under the preregistered rules.

## Integrity checks

For each selected transition, the tool retrieves the baseline and candidate at the exact
selected commits and verifies:

- Git blob SHA equals the selected blob identifier;
- SHA-256 of exact file bytes equals the selected digest;
- the retrieved artifact is still a JSON object;
- deterministic selection identity/key invariants remain intact.

The selection itself is schema-validated and checked for contiguous ranks,
`selected_case_count`, target/shortfall consistency, duplicate transition IDs, and the
two-per-repository cap recorded in the selection.

## Atomic publication

Materialization occurs in a sibling staging directory. The requested output directory
must not already exist. Only after every selected case has been retrieved, verified, and
the materialization index has passed its schema does the staging directory move into the
requested output path.

A failed retrieval therefore cannot publish a partial directory under the canonical
output name.

## Output

The directory contains:

```text
materialization.json
cases/
  gh-<transition-id>/
    baseline.json
    candidate.json
```

`materialization.json` conforms to:

- `docs/r3-public-materialization.schema.json`

Every artifact record contains the relative vendored path, SHA-256, exact GitHub source
URL, source commit, source blob, and byte size. These fields map directly to the
provenance information required later by the R3 benchmark manifest.

The index is additionally bound to the exact `public-selection.json` bytes by
`source_selection_sha256`.

## Evidence boundary

Successful materialization establishes reproducible source-artifact integrity for the
selected public historical slice only. It does not establish labels, benchmark
performance, external validation, or product correctness.

The next preregistered steps remain blinded review-packet construction, provisional
output-independent adjudication, manifest construction, integrity validation, and the
pre-execution digest lock. PermitDiff must still not be run against these selected cases
before that lock exists.
