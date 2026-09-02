# Comparison methodology

PermitDiff combines two deterministic evidence channels:

1. **observed scenario transitions** — concrete baseline/candidate decisions for the supplied review corpus;
2. **bounded static authority findings** — conservative analysis of policy changes that can expand authority outside the observed corpus.

Neither channel is presented as exhaustive authorization verification.

## Effect ordering

PermitDiff defines a total order from least to most permissive:

```text
deny < require_approval < allow
```

For an observed scenario, a transition to a higher-ranked effect is a privilege expansion. A transition to a lower-ranked effect is a restriction.

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

Policy and action values must be canonicalizable JSON. Non-finite numbers, excessive nesting, unsupported values, and integers that the runtime cannot serialize canonically are rejected as invalid input rather than entering the decision path.

## Bounded static authority analysis

A finite scenario corpus can miss a real authority expansion. PermitDiff therefore compares rule semantics independently of scenario hits for a deliberately bounded subset of the built-in policy language.

The analyzer reasons conservatively about:

- `tools`, `principals`, `agents`, `environments`, and `sources` glob domains;
- finite risk domains;
- optional boolean constraints such as `read_only`, `destructive`, and `open_world`;
- argument-predicate addition and removal;
- bounded containment for numeric upper/lower bounds;
- finite `in` / `not_in` sets;
- selected glob-style `matches` predicates;
- added or removed non-neutral rules;
- default-effect relaxation;
- first-match precedence changes among rules with different effects.

Examples of findings include:

```text
allow on payments.refund  -> allow on payments.*          potential_expansion
amount <= 100             -> amount <= 10000              potential_expansion
deny on payments.*        -> deny on payments.refund      potential_expansion
mixed-effect rule reorder                              -> unknown
```

`potential_expansion` means the bounded model found a policy-level change that can increase authority. `unknown` means the analyzer cannot prove the change non-expanding. An unwaived `unknown` fails closed.

PermitDiff does **not** claim general glob-language containment, theorem proving, or exhaustive reachability. Ambiguous or unsupported containment remains `unknown` instead of being interpreted as safe.

## Structural diff

Reviewers also receive policy structure changes:

- added rule IDs;
- removed rule IDs;
- semantically modified rules with shared IDs;
- reordering among shared rules;
- default-effect changes.

Descriptions and rule IDs are review metadata, not permission semantics. A description-only edit is not reported as a semantic rule modification. A same-position rule rename with otherwise identical semantics does not create an authority finding.

## Rule coverage

Coverage is **observed scenario hit coverage**, not proven policy coverage. A candidate rule is covered when at least one corpus scenario selects it as the first match. A matched earlier rule can shadow a later rule, leaving the later rule uncovered.

A zero-uncovered-rule gate forces each candidate rule to have at least one observed semantic case. It does not prove every action, resource, argument boundary, precedence interaction, or fallback path is represented. Static authority analysis reduces a class of scenario-only false negatives; it does not make the corpus exhaustive.

## Waivers

PermitDiff has two distinct waiver types because observed scenario evidence and policy-level static evidence have different scopes.

An observed-transition waiver requires an exact match on:

- scenario ID;
- baseline effect;
- candidate effect;
- action fingerprint;
- non-expired date.

A static-authority waiver requires an exact match on:

- finding kind;
- finding fingerprint;
- baseline policy digest;
- candidate policy digest;
- non-expired date.

Both require a meaningful reason. An issue URL is optional but recommended. Waiver IDs are unique across both classes, and the gate can fail on unused active waivers so stale authorization does not accumulate.

A transition waiver cannot waive a policy-level authority finding. Static waivers are candidate-digest-bound so a reviewed exception does not silently replay after candidate policy drift.

Waivers do not remove evidence from the comparison report. They only remove the exact matching item from gate enforcement and remain visible in gate metadata.

## Reproducibility

The report includes SHA-256 digests for both policy documents and the corpus. Each scenario transition includes a fingerprint of the normalized action. Static findings also have deterministic fingerprints over their bounded semantic evidence. Serialization uses canonical JSON with sorted keys, compact separators, UTF-8, and invalid numeric values rejected before hashing.

A reproducible run therefore requires the same PermitDiff version, schema semantics, policy documents, corpus, and gate evaluation date.
