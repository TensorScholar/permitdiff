# R3 live execution runbook (procedural documentation only)

## Status

This document is **procedural documentation only**. It grants **no operational
authorization**. No discovery, screening, selection, materialization, review,
locking, execution, or publication may begin on the authority of this document.
Every live phase additionally requires a separately recorded phase authorization
per the closure register (`docs/R3_CLOSURE_BLOCKER_REGISTER.md`), and any
`STOP_REQUIRED` disposition halts all downstream progression.

## 1. Authorization prerequisite

Before any step below, confirm a written phase-authorization record exists that
identifies the authority, permitted activity, scope, prerequisites, exact
commit identities, and stop conditions, and that explicitly resolves the
applicable prohibition in the closure audit. Absent that record: stop.

## 2. Live branch creation

Live capture runs only on `research/r3-live-discovery-v1` (see
`.github/workflows/r3-live-discovery.yml`; no other branch triggers capture):

```bash
git fetch origin
git checkout -b research/r3-live-discovery-v1 <authorized-base-commit>
git push origin research/r3-live-discovery-v1
```

## 3. Base commit verification

The workflow pins `DISCOVERY_BASE_COMMIT` and enforces it in CI:

```bash
git cat-file -e "$DISCOVERY_BASE_COMMIT^{commit}"
git merge-base --is-ancestor "$DISCOVERY_BASE_COMMIT" HEAD
```

The capture checkout must descend from the recorded base. The producer
additionally records `study_repository_commit` as `git rev-parse HEAD` of a
clean tree; a dirty tree fails closed and records nothing.

## 4. Token handling

- Live discovery authenticates only via the ephemeral CI `github.token`
  (`persist-credentials: false`); materialization resolves `GH_TOKEN` or
  `GITHUB_TOKEN` from the environment at runtime.
- Tokens are transport credentials only. They are never written to ledgers,
  selections, materialization indexes, progress snapshots, or artifacts.
- Never export a personal token into a shared shell history; prefer the CI
  job's ephemeral credential.

## 5. Environment checks

- Self-hosted macOS ARM64 runner with `uv` and Python 3.13 (`uv python
  install 3.13`, isolated `.venv`, `uv pip install -e '.[dev]'`).
- Pre-collection gate (must pass before any network use):

```bash
python -m pytest -q --no-cov tests/test_r3_discovery.py tests/test_r3_public_discovery.py
ruff format --check <discovery files> && ruff check <discovery files>
```

## 6. Discovery execution sequence

1. `discover` (public-only entrypoint) writes the raw public discovery v2
   ledger plus a noncanonical `discovery-progress.json` diagnostic snapshot:

```bash
python -m scripts.discover_r3_public_benchmark_candidates discover \
  --output validation/r3-benchmark/exploratory/live-capture-v1/discovery-ledger.json \
  --progress-output validation/r3-benchmark/exploratory/live-capture-v1/discovery-progress.json
```

Exit `0` means a complete frame; exit `2` means an incomplete frame that
**must not** proceed to selection; exit `1` means failure with no output.

2. Automated v2 validation (workflow step, exact bytes only):
   v2 schema conformance, `cb01_contract_version` match,
   `cb01_contract_sha256` over exact committed contract bytes,
   `producer_id` equals the canonical public producer,
   `study_repository_commit` equals the capture checkout HEAD,
   `discovery_complete is true`, and no eligible contaminated transition.
   A `capture-summary.json` records ledger SHA-256, counts, versions, study
   commit, workflow commit, and base commit.
3. Product-execution absence check: the ledger must exist and no
   `permitdiff-results.json` may exist. The capture is uploaded as an
   immutable artifact (`retention-days: 30`; diagnostics-only upload on
   failure with `retention-days: 14`).

## 7. Screening / selection / lineage / materialization order

Strictly in this order, each step gated on the previous exit code:

1. `screen ... prepare` (worksheet, bound to exact ledger bytes; output-blind,
   no PermitDiff).
2. Human screening resolution (eligible/excluded with reviewer + rationale).
3. `screen ... apply` (deterministic screened derivation; fails on any
   pending/missing/extra/contaminated/provenance violation).
4. `select` on the screened ledger (frozen target 18, cap 2, minimum 12;
   below-minimum raises with no output artifact).
5. Lineage construction (binds all four parent byte digests).
6. `materialize` with `--selection` **and** `--lineage` (gates verified
   before the first source fetch; below-minimum, digest, study, visibility,
   blob, and SHA failures leave no partial output).
7. Downstream review chain (packets → adjudications → scenarios → manifest →
   v3 lock) per their frozen CLIs; the v3 lock additionally requires
   `--lineage` and verifies selection, lineage, and study bindings.

## 8. Failure handling

- Any non-zero exit stops the sequence. Never hand-edit evidence: digests
  bind exact bytes, so edited artifacts invalidate the chain — regenerate
  from the failed step instead.
- Incomplete discovery (exit `2`): do not select; investigate caps,
  truncation, or transport failures via the progress snapshot, then rerun.
- Dirty tree / missing git / contract mismatch: resolve the environment,
  never override with manual digests or commits.
- Diagnostics uploads on workflow failure are for triage only and are not
  evidence.

## 9. Rollback rules

- Code rollback is `git revert` of single-packet commits; committed evidence
  is never rewritten (byte bindings forbid it) — a failed corpus version is
  abandoned per the frozen failure dispositions, never patched.
- Each packet (B1–B5, C) reverts independently; reverting materialization
  restores v1 behavior for downstream readers still on v1 (none exist live).

## 10. Evidence retention policy

- Raw exact bytes are the trust root: retain ledger, decisions, screened,
  selection, lineage, and materialization files byte-identical.
- Capture artifacts carry `retention-days: 30`; failure diagnostics `14` days.
- Reviewer identities, rationales, and native permission-rule text in evidence
  are sensitive review material: restrict access, do not publish raw review
  artifacts to public CI summaries.
