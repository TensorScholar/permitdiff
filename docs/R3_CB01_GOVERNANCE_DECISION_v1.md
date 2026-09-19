# R3-CB-01 Governance Decision v1

## Status

Prospective Lead governance decision for R3-CB-01 role separation only.

These rules are prospective. They were not reconstructed from historical intent.
No historical meaning is asserted beyond what the referenced records state.

No operational authorization granted. No readiness accepted. No blocker closed.

## 1. Blocker Owner and Validation Owner

- The Blocker Owner and Validation Owner MAY be the same human.
- Separation of the two roles is preferred.
- Any coincidence MUST be explicitly declared in the later assignment record.

## 2. Independent Reviewer

- The Independent Reviewer MUST be a different human from:
  - the Blocker Owner,
  - the Validation Owner,
  - the Principal Systems Lead / approval authority.
- The Independent Reviewer MUST not have produced or validated the evidence under independent review.
- The Independent Reviewer MUST declare any material conflict.

## 3. Principal Systems Lead

- The Principal Systems Lead MAY also serve as Blocker Owner.
- The Principal Systems Lead MUST NOT act as Independent Reviewer for the same adoption/readiness/closure decision.

## 4. R3_CORPUS_CONSTRUCTION_READY reviewer

- The R3_CORPUS_CONSTRUCTION_READY reviewer MUST be human.
- The R3_CORPUS_CONSTRUCTION_READY reviewer MUST be independent from production and validation of evidence relevant to the construction-readiness decision.
- The R3_CORPUS_CONSTRUCTION_READY reviewer MAY be the same human as the CB-01 Independent Reviewer if independence is preserved and a separate independence declaration is recorded.

## 5. AI / automated agents

- AI and automated agents MAY assist evidence gathering, analysis, testing, and drafting.
- AI and automated agents MUST NOT occupy accountable governance roles:
  - approval authority,
  - Blocker Owner,
  - Validation Owner,
  - Independent Reviewer,
  - R3_CORPUS_CONSTRUCTION_READY reviewer.

## 6. Minimum governance-review conflict rule

A reviewer is disqualified from independent review if they:

- produced the evidence being independently reviewed,
- performed the validation being independently reviewed, or
- have an unresolved material conflict affecting the decision.

Evaluated-human-participant disqualifiers are not imported wholesale into this governance rule.

## 7. Historical/technical status

Reference:

- `docs/R3_CB01_ADOPTION_REVIEW_v1.md`
- commit `0609fdb4322d665a06d412837e52de2cada898e3`

The technical gaps listed in the earlier adoption-review record were subsequently resolved by the CB-01 producer-boundary hardening at `0609fdb`. This governance decision does not rewrite that historical record. Known CB-01 technical readiness blockers are currently none. Governance blockers remain unresolved.

## 8. Lifecycle

Lifecycle states are not advanced by this decision. They remain:

- Governance: UNDER_REVIEW
- Readiness: IN_REVIEW
- Operational: AWAITING_AUTHORIZATION
- Closure: OPEN
