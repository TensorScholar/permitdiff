# R3 exploratory discovery harness

## Status

This document describes the collection tooling for `r3-exploratory-corpus-plan-v1`. The harness implements discovery, provenance capture, mechanical pre-label screening, and deterministic selection. It does **not** execute PermitDiff and does not adjudicate security outcomes.

The scientific order remains:

1. preregister methodology;
2. collect the complete candidate frame;
3. screen using preregistered non-outcome criteria;
4. deterministically select the historical slice;
5. establish output-independent adjudication;
6. lock artifact integrity;
7. only then execute PermitDiff.

## Commands

Live discovery:

```bash
python scripts/discover_r3_benchmark_candidates.py discover \
  --output validation/r3-benchmark/exploratory/discovery-ledger.json
```

GitHub code search is an authenticated/rate-limited public API. The script reads `GH_TOKEN` or `GITHUB_TOKEN` from the environment when available. Tokens are collection credentials only: they must never be committed to the ledger, source tree, review packets, or benchmark artifacts.

A deliberately truncated debug collection may be run with `--max-history-commits`, but any reached history cap marks the ledger incomplete. An incomplete ledger is rejected by the selection command and is not admissible for the preregistered historical slice.

After manual screening changes every retained transition from `pending` to either `eligible` or `excluded` under the fixed exclusion vocabulary, deterministic selection is:

```bash
python scripts/discover_r3_benchmark_candidates.py select \
  --ledger validation/r3-benchmark/exploratory/discovery-ledger.json \
  --output validation/r3-benchmark/exploratory/public-selection.json
```

The default selection target is 18 cases with a maximum of two cases per repository, matching the preregistered plan.

## Machine contracts

The collection output conforms to:

- `docs/r3-discovery-ledger.schema.json`

The deterministic selection output conforms to:

- `docs/r3-public-selection.schema.json`

The schemas record the protocol/plan versions and restrict exclusion reasons to the preregistered vocabulary.

## Discovery frame

The harness expands the five preregistered semantic query concepts over the two exact project paths:

- `.claude/settings.json`
- `.claude/settings.local.json`

Search hits at nested or example/template paths are not admitted merely because their names contain `.claude/settings`. This deliberately chooses a narrower, reproducible frame over subjective path interpretation.

For each exact path discovered on a repository's indexed default branch, the harness enumerates commit history touching that path and pairs adjacent historical versions. It captures:

- repository and path;
- discovery query provenance;
- baseline/candidate commits;
- baseline/candidate Git blob identifiers;
- SHA-256 of exact file bytes;
- file sizes;
- candidate commit timestamp;
- candidate parent count;
- whether the `permissions` subtree changed;
- contamination status;
- deterministic selection key.

No PermitDiff module is imported or invoked.

## Automated exclusions versus manual screening

The harness automatically excludes only conditions that can be established mechanically without product behavior or semantic outcome judgment:

- unavailable artifact/commit provenance;
- malformed JSON artifact state;
- ambiguous multi-parent candidate transition;
- a transition already registered as a pre-exposed engineering control.

A transition whose `permissions` subtree is unchanged is **not** automatically discarded. It remains pending so a reviewer can determine whether another authorization-relevant source surface changed or whether the transition should receive the preregistered `no_authorization_relevant_change` exclusion. This avoids silently filtering outside-projection/unknown candidates.

Pending transitions require manual screening for at least:

- public source-semantic sufficiency;
- sensitive/private content;
- project-scoped interpretation;
- cosmetic duplication;
- authorization relevance outside the `permissions` subtree.

Manual screening must not consult PermitDiff output.

## Completeness controls

`discovery_complete` is false when:

- GitHub reports incomplete code-search results;
- a code-search query exceeds GitHub's 1,000-result API window;
- commit history was intentionally capped and the cap was reached.

The selector refuses an incomplete ledger.

The discovery frame has a documented sampling limitation: GitHub code search discovers files indexed on current repository default branches. Historical settings paths that were deleted before discovery, were never indexed, or exist only on non-default branches are not observable through this frame. This limitation must remain visible in exploratory and confirmatory-design reporting; it must not be described as a random sample of the Claude Code ecosystem.

## Deterministic selection

Every transition receives the preregistered key:

```text
SHA256(repository_url + "\n" + baseline_commit + "\n" + candidate_commit + "\n" + path)
```

Selection sorts eligible, uncontaminated transitions by that key, enforces the two-per-repository cap, and takes the first 18. If fewer than 18 eligible transitions remain, the output records the shortfall; criteria are not relaxed.

The selector recomputes every eligible transition's key and refuses a tampered ledger.

## Research boundary

A successful discovery/selection run demonstrates reproducible corpus construction mechanics only. It does not establish:

- correct semantic labels;
- PermitDiff precision or recall;
- external validation;
- ecosystem prevalence;
- production or commercial validity.

Those claims require the later adjudication, integrity-lock, benchmark execution, and confirmatory phases defined by the R3 protocol.
