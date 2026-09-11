# R3 exploratory corpus preregistration

## Status

**Plan version:** `r3-exploratory-corpus-plan-v1`  
**Protocol:** `r3-benchmark-protocol-v1`  
**Applies to:** exploratory corpus construction only  
**Preregistration point:** before new public-source discovery and before any R3 exploratory PermitDiff execution

This document freezes the discovery, screening, selection, adjudication, contamination, and pre-execution rules for the first real R3 exploratory corpus. It is deliberately committed before new cases are collected so that case membership cannot be selected after observing PermitDiff behavior.

This plan does **not** create confirmatory evidence and does not upgrade PermitDiff beyond `ENGINEERING VERIFIED`.

## Research purpose

The exploratory corpus exists to stress the current bounded authorization-regression model, identify implementation and adapter defects, clarify unsupported semantics, and harden the later confirmatory design.

The exploratory study is not intended to estimate ecosystem-wide prevalence or final product accuracy. Any quantitative results from this corpus are descriptive engineering evidence only.

## Scope frozen for this corpus version

The public historical slice is limited to the currently implemented native source projection: Claude Code project settings processed by `claude-code-project-preapprovals`.

The adapter currently models only a narrow preapproval projection under explicit `permissions.defaultMode = "dontAsk"`. It requires `permissions.ask` and `permissions.deny` to remain unchanged across a supported pair, translates only documented supported `permissions.allow` forms, and fails closed on changed semantics it cannot faithfully represent. The corpus must preserve those boundaries rather than filtering inconvenient cases away.

The synthetic slice may also use PermitDiff's canonical policy format to isolate atomic semantic relations, but synthetic cases are always reported separately from public historical cases.

No other source-system adapter is treated as supported in this corpus version.

## Study design

The exploratory corpus has three analytically separate slices.

### Slice A — public historical natural-history slice

Purpose: observe real committed authorization-setting transitions without selecting them by outcome.

Target: **18 selected transitions**, subject to source availability and the rules below.

Rules:

- no target quota by positive/negative/unknown label;
- maximum two selected transitions per repository;
- labels are assigned only after membership is selected;
- all eligible transitions enter the candidate ledger before deterministic selection;
- if fewer than 18 eligible transitions exist, use all eligible transitions and report the shortfall rather than relaxing criteria;
- do not replace a selected case because PermitDiff later performs poorly on it.

This slice is the only exploratory slice that may later inform external-validity design. It is still exploratory and must not be used as confirmatory accuracy evidence.

### Slice B — synthetic semantic-coverage slice

Purpose: isolate atomic supported semantics that may be rare in public history.

Target: **8 cases**.

Cases are chosen from gaps left by Slice A, prioritizing currently supported atomic relations such as new allow authority, approval weakening, restrictive removal, scope/tool addition, predicate relaxation, numeric relaxation, default relaxation, and static-authority expansion.

Synthetic cases must be minimal, deterministic, and explicitly labeled `synthetic`. They are coverage evidence, not external-validity evidence.

### Slice C — unsupported/unknown stress slice

Purpose: test whether unsupported or ambiguous semantics remain fail-closed instead of being converted into false-safe or overconfident definite judgments.

Target: **4 cases**.

Cases should exercise documented uncertainty boundaries such as unsupported predicate relations, ambiguous glob ordering, changed native semantics outside the adapter projection, or precedence interactions that cannot be soundly ordered.

Public historical unknown cases discovered naturally remain in Slice A. Slice C exists only to guarantee explicit boundary stress coverage.

### Overall exploratory target

Nominal target: **30 cases** = 18 public historical + 8 synthetic supported-coverage + 4 unsupported/unknown stress cases.

This number is an engineering-discovery target, not a statistical power claim. No significance test or population-generalization claim is permitted from this exploratory set.

## Public-source discovery protocol

### Discovery universe

Search public GitHub repositories for committed Claude Code project settings that contain authorization configuration relevant to the current adapter. Candidate paths include:

- `.claude/settings.json`
- `.claude/settings.local.json` when it is actually committed to a public repository
- equivalent repository-local Claude settings paths only when source provenance and project scope are unambiguous

User-level, managed-enterprise, private, credential-bearing, generated-secret, or customer configuration is excluded.

### Fixed discovery query concepts

The discovery process must record the exact query, timestamp, and returned repository/path before screening. Initial query concepts are frozen to source semantics rather than PermitDiff terminology:

1. `defaultMode dontAsk permissions allow`
2. `permissions allow ask deny .claude settings`
3. `WebFetch domain permissions allow`
4. `Bash permissions allow .claude`
5. `WebSearch permissions allow .claude`

Equivalent API escaping or quoting is allowed, but the semantic query must not be changed because of observed PermitDiff results.

Additional query concepts require a new plan version or an explicit exploratory amendment committed before cases discovered through those queries are executed.

### Candidate ledger requirement

Every discovered candidate that reaches screening must be retained in a machine-readable discovery ledger, including rejected candidates. The ledger must record at least:

- discovery query identifier;
- discovery timestamp;
- repository URL;
- path;
- candidate commit;
- candidate blob when available;
- baseline parent commit selected for screening;
- baseline blob when available;
- screening status;
- exclusion reason when rejected;
- contamination status;
- deterministic selection key for eligible transitions.

This prevents silent deletion of inconvenient candidates.

## Transition enumeration

For each discovered repository/path, enumerate committed changes to that path without consulting PermitDiff output.

A transition is one baseline/candidate pair where:

- candidate is a public immutable commit containing the relevant file;
- baseline is the immediately preceding unambiguous version of the same file in history;
- both file states can be retrieved and hashed;
- the transition can be represented as one review unit.

Merge commits with ambiguous parent choice are excluded unless the relevant file has an unambiguous first-parent transition and that parent-selection rule is recorded before adjudication.

Do not construct an artificial baseline by manually editing the candidate for Slice A.

## Pre-label screening criteria

Screening occurs before semantic adjudication and before PermitDiff execution.

A public historical transition is eligible when all of the following hold:

1. repository, commit, and file are publicly retrievable;
2. both baseline and candidate bytes are immutable and reproducible;
3. both artifacts are valid JSON files within the Claude settings family;
4. at least one authorization-relevant source field changes or the transition is intentionally retained as an outside-projection control;
5. enough public source-system documentation exists to support later review;
6. the transition contains no private data or credentials;
7. it is not a cosmetic duplicate of another transition from the same commit history.

Eligibility must **not** depend on whether PermitDiff accepts, blocks, passes, or reports unknown for the case.

### Fixed exclusion reasons

Rejected candidates must use one or more of these reasons:

- `unavailable_provenance`
- `ambiguous_parent_transition`
- `artifact_parse_failure`
- `no_authorization_relevant_change`
- `duplicate_transition`
- `insufficient_public_semantics`
- `private_or_sensitive_content`
- `non_project_or_unscoped_settings`
- `pre_exposed_engineering_control`

New exclusion reasons require an explicit plan amendment and must not be introduced post hoc to remove poor product outcomes.

## Deterministic selection from eligible public history

After the eligible candidate ledger is frozen, selection is deterministic and label-blind.

For every eligible transition, compute:

`selection_key = SHA256(repository_url + "\n" + baseline_commit + "\n" + candidate_commit + "\n" + path)`

Then:

1. sort candidates by `selection_key` ascending;
2. take candidates in that order;
3. enforce a maximum of two selected cases per repository;
4. stop at 18 selected public historical transitions;
5. preserve all non-selected eligible candidates in the ledger.

This is not random population sampling. It is a reproducible anti-cherry-picking mechanism for a curated public candidate pool.

No selected case may be replaced after PermitDiff output is observed. A provenance failure discovered before execution may cause exclusion only under a preregistered exclusion rule and must remain visible in the ledger.

## Contamination register

A source is contaminated for unbiased exploratory membership if PermitDiff engineering already used the same transition or source pair before this preregistration.

The existing external-repository validation uses `SpearIT-LLC/project-framework`, baseline commit `28133b63a9a54621c8d7be879ba671daf8464c1c`, candidate commit `d8a47de7f5f96d501432a7f02c6909c667a5f31d`, path `.claude/settings.local.json`.

That transition is therefore **excluded from Slice A selection** and may only be retained as a separately reported `pre_exposed_engineering_control` for harness regression checks.

PermitDiff's own fixtures, examples, and previously hand-authored validation artifacts are likewise excluded from the public historical slice.

The contamination register must grow, never shrink, when prior exposure is discovered.

## Ground-truth adjudication protocol

### Independence from PermitDiff

No reviewer may see PermitDiff output for a case before that reviewer's label is recorded.

Case packets must contain only:

- baseline and candidate source artifacts;
- a plain textual diff;
- immutable provenance;
- relevant public source-system documentation;
- a fixed review question and label definitions.

They must not contain PermitDiff-normalized plans, findings, gate outcomes, or product-generated explanations.

### Labels

Each case receives exactly one review-level label:

- `SECURITY_RELEVANT_REGRESSION`
- `BENIGN_OR_RESTRICTIVE_CHANGE`
- `UNKNOWN_OR_UNSUPPORTED`

Positive cases additionally receive one or more atomic categories. Genuine ambiguity remains `UNKNOWN_OR_UNSUPPORTED`; reviewers must not force a binary answer.

### Reviewer separation

For exploratory work, a singly reviewed case is allowed only when the rationale is explicit and reproducible, and it remains marked `single_reviewed`.

AI assistance, including the system constructing this corpus, may help with curation, provenance extraction, or drafting a review packet, but **must not be represented as an independent human reviewer** and cannot satisfy Reviewer B for confirmatory evidence.

Before a confirmatory maturity claim, independent human review should be obtained where feasible, disagreements adjudicated before execution, and singly reviewed cases reported separately.

### Adjudication record

Before PermitDiff execution, every selected case must record:

- final provisional exploratory label;
- support-boundary expectation;
- atomic categories where applicable;
- reviewer identity/status;
- rationale tied to source artifacts/documentation;
- evidence references;
- ambiguity notes;
- adjudication timestamp or version marker.

Any label change made after PermitDiff output is seen is contamination. The original label and reason for revision must remain auditable, and the revised case cannot be treated as output-independent evidence in that corpus version.

## Pre-execution integrity lock

PermitDiff must not be run against the selected exploratory cases until all of the following are committed:

1. complete candidate discovery ledger;
2. deterministic selected-case list;
3. immutable vendored or reproducibly retrievable baseline/candidate artifacts;
4. SHA-256 digests and source commit/blob provenance;
5. provisional exploratory adjudication records;
6. case manifest conforming to the canonical schema;
7. integrity-validator output for the manifest and artifacts.

The manifest digest produced by the merged R3 integrity validator becomes the exploratory pre-execution reference.

If any of these change after first product execution, create a new exploratory corpus version rather than silently rewriting the prior evidence state.

## Source documentation discipline

Ground truth must rely on publicly documented source semantics or unambiguous artifact logic. Documentation URLs and, where possible, version/date context must be retained.

Do not infer vendor runtime behavior that is undocumented. If runtime state, policy precedence, sandbox behavior, managed overrides, hooks, plugins, or other omitted surfaces materially affect the label and cannot be resolved from public evidence, classify the case as `UNKNOWN_OR_UNSUPPORTED`.

## Data handling and repository hygiene

- No credentials, tokens, private repository data, customer artifacts, or personally sensitive content.
- Vendored public fixtures should contain only the minimum source bytes necessary to reproduce the review unit.
- Preserve license/provenance metadata where required.
- Do not execute code from candidate repositories merely to collect a settings transition.
- Artifact collection is read-only with respect to external repositories.
- Discovery tooling must not require private credentials for the final reproducibility path.

## Exploratory analysis policy

Once the pre-execution lock is established, PermitDiff may be run and changed in response to exploratory findings.

However:

- report raw case outcomes, not only aggregate percentages;
- keep public historical, synthetic supported, and unknown stress slices separate;
- never report exploratory precision/recall as confirmatory product accuracy;
- every false negative, false positive, overconfident unknown, execution failure, or provenance failure receives an error-classification record;
- a product fix triggered by a case must reference that exploratory case, making adaptation visible;
- reruns after fixes are new exploratory run versions, not replacements for the original output.

## Stop conditions

Stop corpus construction and amend/version this plan before continuing if:

- the current adapter boundary proves materially different from the preregistered source universe;
- candidate discovery yields a systematic source type not covered by the fixed screening rules;
- source licensing or privacy makes vendoring unsafe;
- deterministic selection cannot be reproduced from the ledger;
- case labels depend materially on unavailable runtime state;
- the selected historical pool is too small to exercise the intended research question.

Do not solve these problems by silently relaxing criteria.

## Reproducibility artifacts required before first exploratory execution

The repository must contain:

- this plan and its machine-readable companion;
- complete discovery ledger, including rejections;
- selected-case manifest;
- baseline/candidate artifacts or immutable retrieval references;
- source commit/blob IDs;
- SHA-256 digests;
- review packets and adjudication records;
- integrity-validator evidence;
- contamination register;
- exact corpus version identifier.

## Immediate execution sequence after this plan merges

1. Execute only the frozen discovery queries and build the full candidate ledger.
2. Screen candidates using only preregistered non-outcome criteria.
3. Freeze the eligible pool and compute deterministic selection keys.
4. Select Slice A without seeing PermitDiff outputs or labels.
5. Vendor/retrieve exact source artifacts and provenance.
6. Build blinded review packets.
7. Record provisional exploratory adjudications independently of PermitDiff.
8. Add synthetic Slice B and unknown Slice C only for documented taxonomy gaps.
9. Build the canonical exploratory manifest and run the integrity validator.
10. Commit the pre-execution corpus state and digest.
11. Only then implement/run the benchmark execution and text-diff baseline harness.

This ordering is intentionally slower than directly running examples. The delay is a validity control: it preserves a clean distinction between case selection, ground truth, product execution, and later engineering adaptation.
