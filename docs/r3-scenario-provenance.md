# R3 scenario provenance and channel availability

## Status

This contract operationalizes the scenario-provenance section of
`r3-exploratory-measurement-contract-v2` before canonical R3 product execution.

The configuration transition and its scenario corpus are separate experimental objects.
A configuration case can therefore remain valid when the primary observed-scenario channel
is absent. PermitDiff must not manufacture answer-informed scenarios merely to make that
channel available.

The canonical pre-execution artifact is a scenario-channel set conforming to:

- `docs/r3-scenario-channel-set.schema.json`
- schema version `permitdiff.dev/r3-scenario-channel-set/v1`

## Provenance classes

Every scenario set must record exactly one frozen provenance class:

- `PREEXISTING_PROJECT` — existed independently of this benchmark before case adjudication;
- `INDEPENDENT_BLIND` — authored without PermitDiff output and without the case ground-truth
  decision;
- `DIAGNOSTIC_ANSWER_INFORMED` — authored with knowledge of the expected semantic relation
  or specifically to witness it;
- `PRODUCT_GENERATED` — produced by PermitDiff or a PermitDiff-coupled generator.

Primary-comparison admissibility is derived from provenance, not selected after outcomes:

- `PREEXISTING_PROJECT` and `INDEPENDENT_BLIND` are primary-admissible;
- `DIAGNOSTIC_ANSWER_INFORMED` and `PRODUCT_GENERATED` are diagnostic-only.

A diagnostic-only set never makes `scenario_channel_availability` true for the primary
comparison.

`PRODUCT_GENERATED` scenarios, if introduced in a later evaluated method, require explicit
generation-cost accounting. They are prohibited from the pre-execution scenario registry
because the R3 protocol forbids product execution before the lock.

## Explicit absent channel

Each case records `primary_channel_state` as `PRESENT` or `ABSENT` after provenance review.

`PRESENT` is valid only when at least one scenario set has primary-admissible provenance.

`ABSENT` is valid only when no primary-admissible scenario set exists. The case must then
record:

`absence_reason = NO_PRIMARY_ADMISSIBLE_SCENARIO_SET`

Diagnostic scenario sets may coexist with an absent primary channel. They remain available
for debugging/mechanism analysis but are excluded from primary observed-channel claims.

Absence is not a benchmark failure and is not imputed as a negative product result. It is
reported through `scenario_channel_availability` and the static channel may still be
evaluated independently.

## Workflow

After deterministic public materialization, prepare a provenance worksheet without
creating scenario files:

```bash
python scripts/build_r3_scenario_channels.py prepare \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --output validation/r3-benchmark/exploratory/scenario-channels-v1.json
```

The worksheet is bound to the exact materialization bytes and starts every case in
`pending` state with an empty `scenario_sets` array. Preparing it does not create a
scenario directory or corpus.

For a case with a real scenario set, materialize the exact scenario artifact under the
case evidence root, record its digest and provenance evidence, then set the case to
`decided`. Scenario artifacts use paths below:

`cases/<transition-id>/scenarios/`

For a case with no primary-admissible scenario set, set the case to `decided`, record
`primary_channel_state = ABSENT`, keep all primary-admissible sets absent, and use the
frozen absence reason. Do not create placeholder scenario files.

Validate the completed artifact before the pre-execution lock:

```bash
python scripts/build_r3_scenario_channels.py validate \
  --materialization \
    validation/r3-benchmark/exploratory/public-historical-v1/materialization.json \
  --scenario-channels validation/r3-benchmark/exploratory/scenario-channels-v1.json
```

Validation enforces exact membership/order, materialization digest binding, provenance-
derived admissibility, explicit present/absent state, artifact containment, and SHA-256
integrity.

## Evidence boundary

This is provenance/evidence preparation only. It does not execute PermitDiff, score a
case, or upgrade maturity.

The scenario-channel set becomes part of the pre-execution evidence chain. The lock must
bind its exact bytes before product execution; that binding is implemented in the next
pre-execution-lock task.
