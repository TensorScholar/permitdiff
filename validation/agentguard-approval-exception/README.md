# AgentGuard scoped approval-exception validation pilot

This pilot tests PermitDiff against a real historical authorization change from
`TensorScholar/agentguard`. It is intentionally narrow: the source change added
scoped approval exceptions that can turn a previously approval-gated action into
an allowed action.

## Frozen source evidence

- Source repository: `TensorScholar/agentguard`
- Baseline commit: `0b65e4dc7d3069471b005da8d29297586f1d5f64`
- Candidate commit: `0ebd301db4fcc20c97b0866cd05360ebf3499c7d`
- Candidate commit title: `Add scoped approval exceptions`
- Source policy example: `examples/policy_with_exception.yaml`
- Source authorization implementation: `agentguard/policy.py`

The historical candidate added an approval exception scoped to `run_*` tools and
the `shell_execution` capability. In the source implementation, a matching,
non-hard-denied exception returns `ALLOW`; before that change, the same capability
followed the approval-required path.

`source.json` records this ground truth and the normalization boundary before the
PermitDiff assertions are evaluated.

## Deterministic normalization

The pilot does not attempt to reproduce AgentGuard's runtime authorization stack.
It projects only the permission semantics needed for this historical claim:

```text
AgentGuard capability: shell_execution
        |
        v
arguments._agentguard.capabilities = ["shell_execution"]
        |
        +-- baseline: require_approval
        |
        +-- candidate + tool run_*: allow
```

AgentGuard hard-deny rules precede approval exceptions. Calls that would hit those
hard denies are therefore outside this pilot corpus. The pilot does not model
credential issuance, runtime execution, approval orchestration, external state, or
all AgentGuard policy semantics.

## Pre-registered expected outcomes

| Scenario | Baseline | Candidate | Purpose |
|---|---|---|---|
| `scoped-run-status` | `require_approval` | `allow` | Positive historical approval-bypass case. |
| `nonmatching-shell` | `require_approval` | `require_approval` | Tool-scope negative control. |
| `unrelated-read` | `deny` | `deny` | Unrelated-action negative control. |

The candidate has two explicit rules and both must receive observed corpus hits.
The unrelated case exercises the candidate default, so the pilot also detects an
accidental scope leak that would authorize unrelated actions.

PermitDiff is expected to report:

- one observed privilege expansion;
- one new allow;
- one approval bypass;
- one static `rule_added` potential authority expansion;
- zero static `unknown` findings;
- zero uncovered candidate rules.

The committed strict gate intentionally blocks this comparison. A successful
validation run therefore means the comparison completes deterministically and the
gate rejects the known expansion; gate exit code `2` is the expected CLI result.

## Reproduce

```bash
permitdiff compare \
  validation/agentguard-approval-exception/baseline.yaml \
  validation/agentguard-approval-exception/candidate.yaml \
  validation/agentguard-approval-exception/corpus.jsonl \
  --gate validation/agentguard-approval-exception/gate.yaml \
  --format json
```

The executable regression contract is
`tests/test_validation_pilots.py`.

## Claim boundary

This is **historical normalized retrospective evidence**, not proof of complete
AgentGuard semantics and not evidence that PermitDiff has executed inside an
external repository. It therefore strengthens independent semantic validation but
does **not** by itself satisfy PermitDiff's release-readiness requirement that the
release candidate run successfully in at least one external repository.
