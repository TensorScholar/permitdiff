# Research-Derived Product and Hardening Roadmap

This roadmap converts PermitDiff's technical audits and market/novelty review into implementation phases. It is intentionally evidence-driven: each phase must close a concrete product, security, scientific-defensibility, or commercial-adoption gap and must ship through an isolated pull request with reproducible validation.

## Product thesis

PermitDiff is a **release-time semantic permission regression gate for AI-agent authority changes**.

The defensible claim is narrower than "proof of effective authority":

- observed analysis evaluates effective decisions for the supplied review corpus;
- bounded static analysis compares declared policy semantics conservatively and fails closed on unsupported or ambiguous relations;
- current analysis does not prove exhaustive global first-match reachability, satisfiability, or the complete effective allow-set of an arbitrary policy;
- runtime authorization, credential binding, execution integrity, and action enforcement remain outside PermitDiff and belong to AgentGuard-style runtime controls.

The commercial wedge is CI/release assurance: answer **"does this proposed permission change grant materially more authority, remove an approval boundary, widen scope, weaken constraints, or create unresolved authorization uncertainty?"** before merge or release.

## Rating target

A credible ~4.5/5 product/research rating should be earned by evidence rather than positioning language.

| Dimension | 4.5/5 evidence bar |
|---|---|
| Claim accuracy | User-facing outputs make the bounded-analysis boundary explicit; no exhaustive-safety implication. |
| Technical defensibility | Known silent paths are pinned by invariants/property tests; strict profiles cannot silently disable critical evidence checks. |
| Novelty | Clear differentiation from text diff, generic policy-as-code, runtime authorization, and generic agent security scanners; semantic authority regression remains the primary unit of analysis. |
| Reliability | Deterministic, fail-closed semantics; exact digest-bound waivers; reproducible reports; high recall for supported atomic broadening classes. |
| Commercial readiness | Native adapters, real public validation cases, actionable CI output, migration/onboarding path, documented buyer/use-case boundary. |
| Defensibility/moat | Public regression corpus, adapter normalization know-how, authority-change taxonomy, reproducible benchmark/evidence suite, and historical validation dataset. |

## Completed foundations

### Transition waiver integrity — complete

- transition waivers bind to baseline and candidate digests;
- stale approvals cannot replay across different policy states.

### Differential evidence integrity — complete

- strict gates can require observed privilege-expansion evidence for unwaived static potential expansions;
- unrelated transitions do not satisfy the evidence requirement;
- static authority waivers and transition waivers remain distinct review channels.

## Phase R1 — Claim-boundary hardening

**Goal:** make the product's strongest public claim scientifically accurate in every primary output.

Deliverables:

1. Add a concise analysis-boundary statement to Markdown and console reports.
2. Add equivalent machine-readable SARIF run metadata/help text so code-scanning consumers cannot mistake a clean report for exhaustive authorization proof.
3. Pin wording with reporting tests.
4. Keep README/limitations/methodology terminology aligned:
   - observed corpus evidence;
   - bounded static declared-authority over-approximation;
   - not an exhaustive effective-authority proof.

Acceptance criteria:

- every human-facing report states the analysis boundary;
- SARIF contains the boundary in run/tool metadata;
- tests prevent accidental removal or overclaiming;
- no behavioral gate semantics change in this phase.

## Phase R2 — Strict-profile integrity

**Goal:** prevent strict review from being weakened by silent coverage disablement.

Deliverables:

1. Treat `max_uncovered_candidate_rules = null` as an explicit non-strict escape, never an implicit strict behavior.
2. Add an explicit acknowledgement or strict-profile validation for disabled candidate-rule coverage.
3. Surface the escape in gate results/evidence.
4. Add regression tests for modified-policy and added-rule cases.
5. Review pre-existing permissive default effects and expose them explicitly in strict mode.

Acceptance criteria:

- `strict_gate()` cannot silently disable candidate coverage;
- custom gates that disable coverage must do so explicitly and audibly;
- changed policies cannot receive a strict PASS merely because hit-count coverage was disabled.

## Phase R3 — Precedence and reachability hardening

**Goal:** reduce the gap between per-rule declared analysis and first-match effective behavior without pretending to be a full solver.

Deliverables:

1. Detect insertion/removal precedence shifts across mixed-effect boundaries.
2. Emit `UNKNOWN` when an added/removed/reordered rule may change first-match authority and disjointness cannot be proven.
3. Add conservative reachability/dead-code diagnostics to reduce false-positive waiver pressure.
4. Never suppress a security finding solely because reachability is uncertain.

Acceptance criteria:

- added `ALLOW`/`REQUIRE_APPROVAL` before relevant restrictive rules cannot pass silently;
- removal of a restrictive predecessor cannot pass silently;
- provably disjoint insertions avoid unnecessary blocking where the bounded model can establish disjointness;
- ambiguous cases remain fail-closed.

## Phase R4 — Recall and soundness property suite

**Goal:** turn semantic safety assumptions into executable invariants.

Deliverables:

1. Property/fuzz tests for atomic broadening classes:
   - tool/scope addition;
   - predicate removal;
   - numeric bound relaxation;
   - restrictive-rule narrowing/removal;
   - default relaxation;
   - new allow/approval-bypass insertion;
   - cross-effect changes.
2. Non-expansion differential tests for known safe restrictions.
3. Predicate-operator allowlist invariant: unsupported relations must resolve to `UNKNOWN`, never silent-safe.
4. Glob-relation soundness checks against a bounded brute-force witness universe.

Acceptance criteria:

- every supported atomic broadening family has a strict-gate recall property;
- unsupported operators cannot accidentally become silent-safe;
- failures shrink to reproducible counterexamples.

## Phase R5 — Bounded semantic precision

**Goal:** lower false positives without weakening fail-closed behavior.

Candidate work, only where soundness can be demonstrated:

- better same-effect `REQUIRE_APPROVAL` scope reasoning;
- safe predicate relation expansion for explicitly supported operator pairs;
- improved rename/move normalization;
- better glob witnesses;
- reachability-informed explanatory diagnostics.

Non-goal: general SMT-style exhaustive authorization solving unless a later research phase establishes a tractable, auditable subset with clear performance bounds.

## Phase R6 — Adapter and ecosystem expansion

**Goal:** strengthen commercial usefulness while preserving one semantic core.

Priority adapters should be selected by evidence of real permission-review demand, not by ecosystem breadth alone.

Required qualities for every adapter:

- documented projection boundary;
- canonical normalization evidence;
- fail-closed handling of unmodeled changed semantics;
- public fixtures or validation cases;
- no claim that a projection represents the platform's complete runtime authority.

Claude Code remains the reference native projection. Candidate ecosystems may include MCP permission/configuration surfaces and other agent tool-policy formats where a stable, reviewable authorization surface exists.

## Phase R7 — Public validation and commercial evidence

**Goal:** make differentiation measurable rather than rhetorical.

Deliverables:

1. Maintain a versioned corpus of historical/public permission regressions.
2. Publish baseline-vs-PermitDiff detection evidence with exact commits/configuration.
3. Measure:
   - supported-change recall;
   - `UNKNOWN` rate;
   - false-positive rate on reviewed cases;
   - runtime/CI latency;
   - waiver frequency and causes.
4. Add at least three qualitatively different public validation cases.
5. Document buyer workflows:
   - platform/security engineering;
   - AI infrastructure teams;
   - application teams reviewing agent tool permissions;
   - regulated release/change-control environments.

Acceptance criteria:

- novelty claims cite demonstrated behavior and comparison scope;
- benchmark data is reproducible from the repository;
- commercial claims distinguish product capability from consulting/private-adapter services.

## Phase R8 — Release and adoption readiness

**Goal:** remove non-product blockers to real installation and evaluation.

Deliverables:

- restore/verify PyPI Trusted Publisher identity and release publication path;
- ship an installable release containing the post-rc2 hardening work;
- ensure starter workflow uses a released immutable version;
- publish migration notes for any gate-schema breaking changes;
- verify external-repository installation and CI examples from the released wheel.

## Commercial positioning guardrails

Prefer:

> Semantic permission regression testing for AI-agent releases.

> Detect observed privilege expansion and conservative policy-level authority widening before merge.

> Deterministic CI evidence for permission changes, approval bypasses, scope widening, constraint weakening, and unresolved authorization uncertainty.

Avoid until a future solver/proof phase exists:

> Proves effective authority is safe.

> Exhaustively computes all authority an agent can reach.

> Guarantees runtime authorization safety.

## Portfolio boundary

PermitDiff owns **release-time semantic permission regression and evidence**.

It should not absorb:

- runtime action authorization or execution integrity (AgentGuard);
- generic model/output regression evaluation (ProofDiff);
- broad identity-provider or credential-broker functionality;
- generic vulnerability scanning unrelated to permission-change semantics.

This boundary is strategically important: expanding outside it would weaken the product thesis and reduce both novelty and commercial clarity.

## Execution discipline

Every implementation phase must:

1. start from canonical `main`;
2. use an isolated branch and pull request;
3. preserve deterministic/fail-closed behavior;
4. add tests before changing a security claim;
5. update schema/docs when public contracts change;
6. pass the repository's protected CI checks;
7. merge before starting the next dependent phase;
8. synchronize local `main` with `origin/main` after merge and delete the completed topic branch.
