# R3 output-blind public screening

## Status

This document defines the operational screening handoff for
`r3-exploratory-corpus-plan-v1`. It does not change the preregistered eligibility or
exclusion rules. It makes manual screening explicit, ledger-bound, reproducible, and
machine-checkable before deterministic selection.

The screening tooling does **not** import or execute PermitDiff and must not use product
output when resolving decisions.

## Prepare a screening worksheet

Start only from a complete public discovery ledger:

```bash
python scripts/screen_r3_public_benchmark_candidates.py prepare \
  --ledger validation/r3-benchmark/exploratory/discovery-ledger.json \
  --output validation/r3-benchmark/exploratory/screening-decisions.json
```

The worksheet contains exactly the transitions whose discovery-ledger
`screening_status` is `pending`. Mechanically excluded transitions remain in the source
ledger and are not re-opened by this workflow.

The worksheet is bound to the exact source-ledger bytes by `source_ledger_sha256`.
Changing the ledger after worksheet generation invalidates the worksheet rather than
silently transferring decisions to a different candidate frame.

## Manual resolution

For every worksheet entry, change `decision` from `pending` to exactly one of:

- `eligible`
- `excluded`

Every resolved entry requires a non-empty `reviewer` and `rationale`.

An `eligible` decision must have an empty `exclusion_reasons` array.

An `excluded` decision must contain one or more reasons from the frozen preregistered
vocabulary:

- `unavailable_provenance`
- `ambiguous_parent_transition`
- `artifact_parse_failure`
- `no_authorization_relevant_change`
- `duplicate_transition`
- `insufficient_public_semantics`
- `private_or_sensitive_content`
- `non_project_or_unscoped_settings`
- `pre_exposed_engineering_control`

Screening is output-blind. Do not inspect PermitDiff-normalized policies, findings, gate
outcomes, or explanations while resolving the worksheet.

AI assistance may curate or document screening evidence, as permitted by the
preregistration. This screening record is not an independent human ground-truth review
and must not be represented as Reviewer B evidence.

## Apply completed decisions

Apply the complete worksheet to the exact ledger it was prepared from:

```bash
python scripts/screen_r3_public_benchmark_candidates.py apply \
  --ledger validation/r3-benchmark/exploratory/discovery-ledger.json \
  --decisions validation/r3-benchmark/exploratory/screening-decisions.json \
  --output validation/r3-benchmark/exploratory/screened-discovery-ledger.json
```

Application fails closed when:

- the discovery frame is incomplete;
- the worksheet is bound to different ledger bytes;
- any pending transition lacks a decision;
- a worksheet targets a transition that was not pending;
- repository/path/commit metadata was changed in the worksheet;
- a selection key is inconsistent with immutable transition identity;
- an exclusion reason is outside the preregistered vocabulary;
- a resolved entry still says `pending`;
- an eligible transition is contaminated;
- an eligible transition lacks immutable baseline/candidate artifact provenance.

The screened output remains a `permitdiff.dev/r3-discovery-ledger/v1` document. The
tool changes only screening resolution fields for originally pending transitions:
`screening_status`, `exclusion_reasons`, and `manual_review_required`.

## Deterministic selection

Only after the screened ledger contains no pending transitions may Slice A selection
proceed:

```bash
python scripts/discover_r3_public_benchmark_candidates.py select \
  --ledger validation/r3-benchmark/exploratory/screened-discovery-ledger.json \
  --output validation/r3-benchmark/exploratory/public-selection.json
```

Selection remains label-blind and uses the frozen SHA-256 ordering with the two-case
per-repository cap and target of 18. Screening does not relax a shortfall.

## Machine contract

Screening worksheets conform to:

- `docs/r3-screening-decisions.schema.json`

The schema is intentionally separate from the discovery-ledger schema. This preserves
the raw discovery artifact while retaining an auditable record of who resolved each
manual screening decision and why.

## Evidence boundary

Completing this workflow establishes only a reproducible, output-blind candidate
screening step. It does not establish semantic ground truth, PermitDiff accuracy,
external validation, or production validity.

After deterministic selection, the preregistered sequence still requires exact source
artifacts/provenance, blinded review packets, provisional adjudications, the canonical
benchmark manifest, integrity-validator evidence, and a pre-execution digest lock before
any PermitDiff run.
