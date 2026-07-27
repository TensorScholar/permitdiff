# Architecture

## Design goal

PermitDiff provides a deterministic, inspectable answer to a narrow question: how do effective tool permissions change between two policy versions over an explicit scenario corpus?

The architecture is a modular monolith. Distribution would add operational complexity without improving the core comparison. All commands run locally and require no service, database, queue, or network dependency.

## Data flow

```text
baseline.yaml ─┐
               ├─> strict loaders ─> immutable models ─┐
candidate.yaml ┘                                       │
                                                       ├─> policy engines
corpus.jsonl ───> bounded streaming loader ────────────┘        │
                                                                v
                                                       semantic comparison
                                                                │
                                    ┌───────────────────────────┼──────────────┐
                                    v                           v              v
                              structural diff             rule coverage   transitions
                                    └───────────────────────────┼──────────────┘
                                                                v
permitdiff-gate.yaml ─> strict gate loader ─────────────> waiver + threshold gate
                                                                │
                                                                v
                                              console / JSON / Markdown / SARIF
```

## Components

| Module | Responsibility |
|---|---|
| `models.py` | Immutable action, scenario, annotation, risk, and decision models. |
| `policy.py` | Versioned policy schema, strict loading, validation, and canonical digest. |
| `predicates.py` | Side-effect-free matching over action fields and arguments. |
| `engine.py` | Deterministic first-match evaluation and trust-boundary enforcement. |
| `corpus.py` | Bounded JSONL parsing, validation, duplicate detection, and errors. |
| `analysis.py` | Effective transition classification, structural diff, and coverage. |
| `gate.py` | Exact waivers, expiry handling, thresholds, and release verdict. |
| `reporting.py` | Stable human and machine report formats. |
| `cli.py` | Thin command adapter and stable exit-code contract. |
| `resources.py` | Safe materialization of the bundled starter project. |

## Important invariants

1. **Same input, same output.** No current time is used except waiver expiry; gate evaluation accepts an explicit date for reproducible tests.
2. **No probabilistic judge.** An LLM never decides whether a permission change is safe.
3. **First match is explicit.** Rule ordering is policy semantics, not implementation detail.
4. **Trust is explicit.** MCP-style annotations cannot authorize an action unless the policy also requires trusted security metadata.
5. **Waivers are narrow.** A waiver binds scenario ID, baseline effect, candidate effect, and expiry.
6. **Unknown input fails.** Schemas reject unexpected fields instead of ignoring typos.
7. **Reports carry evidence.** Policy/corpus digests and action fingerprints identify the compared artifacts.

## Why a scenario corpus

A general symbolic equivalence checker would be attractive in theory but substantially increases language constraints and implementation risk. A corpus-based design is practical, reviewable, and compatible with production incident cases. It also makes coverage gaps visible instead of implying completeness.

PermitDiff therefore separates two concerns:

- semantic comparison over observed/curated cases;
- coverage quality as an explicit release metric.

This is not formal verification. The limitation is intentional and documented.

## Scalability

Runtime is `O(S × (B + C))`, where `S` is the number of scenarios and `B`/`C` are baseline/candidate rule counts. This is appropriate for CI-scale corpora and policy documents. The current implementation favors transparent sequential execution over concurrency because policy evaluation is CPU-light and deterministic; parallelism would complicate ordering, error reporting, and profiling before evidence shows it is needed.

The corpus loader is bounded at 50 MB and 100,000 scenarios. See `benchmarks/results` for reproducible measurements.

## Extension boundaries

Good extension points:

- adapters that normalize external authorization formats into `PolicyDocument`;
- corpus generators outside the trusted decision path;
- richer report consumers;
- additional deterministic predicates with explicit tests and schema versions.

Rejected extension points for the core:

- arbitrary Python policy plugins;
- networked policy evaluation;
- model-based policy adjudication;
- embedded runtime enforcement;
- stateful approvals or identity management.

These belong in separate systems and would weaken PermitDiff's reviewability.
