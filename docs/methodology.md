# Comparison methodology

## Effect ordering

PermitDiff defines a total order from least to most permissive:

```text
deny < require_approval < allow
```

A transition to a higher-ranked effect is a privilege expansion. A transition to a lower-ranked effect is a restriction.

| Baseline | Candidate | Direction | Special classification |
|---|---|---|---|
| deny | require_approval | expanded | — |
| deny | allow | expanded | new allow |
| require_approval | allow | expanded | new allow and approval bypass |
| allow | require_approval | restricted | — |
| allow | deny | restricted | — |
| require_approval | deny | restricted | — |

Severity also incorporates the scenario risk label. Risk is review metadata supplied by the corpus owner; it does not change policy evaluation.

## Policy evaluation

Rules are evaluated in document order. The first matching rule returns its effect. If no rule matches, `default_effect` applies.

Within a match dimension, values are ORed. Across dimensions, configured requirements are ANDed. Argument predicates resolve dotted paths and support deterministic scalar/list comparisons and glob matching.

## Structural diff

Semantic diff is the primary signal, but reviewers also need policy structure changes:

- added rule IDs;
- removed rule IDs;
- modified rules with shared IDs;
- reordering among shared rules;
- default-effect changes.

Structural changes can matter even when the current corpus shows no effect change. That is why uncovered candidate rules are gateable.

## Rule coverage

Coverage is observed hit coverage, not code coverage. A candidate rule is covered when at least one corpus scenario selects it as the first match. A matched earlier rule can shadow a later rule, leaving the later rule uncovered.

A zero-uncovered-rule gate forces each candidate rule to have at least one observed semantic case. It does not prove every branch or boundary is represented.

## Waivers

Waivers are applied only to privilege expansions and require an exact match on:

- waiver ID;
- scenario ID;
- baseline effect;
- candidate effect;
- non-expired date.

Reason is mandatory and must contain meaningful text. An issue URL is optional but recommended. The gate can fail on unused active waivers so stale authorization does not accumulate.

Waivers do not hide the transition from the report; they remove it from configured expansion thresholds and remain visible in gate metadata.

## Reproducibility

The report includes SHA-256 digests for both policy documents and the corpus. Each scenario transition includes a fingerprint of the normalized action. Serialization is canonical JSON with sorted keys, compact separators, UTF-8, and non-finite numbers rejected.

A reproducible run therefore requires the same PermitDiff version, schema semantics, policy documents, corpus, and gate evaluation date.
