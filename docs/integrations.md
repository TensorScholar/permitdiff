# Integrations

## GitHub Actions

`permitdiff init` includes a minimal workflow. For this repository, `.github/workflows/ci.yml` demonstrates a fuller matrix and artifact flow.

A robust integration should:

1. compare the merge-base policy and proposed policy over the same committed corpus;
2. write Markdown/JSON/SARIF before checking the exit code;
3. preserve reports as workflow artifacts;
4. upload SARIF with `github/codeql-action/upload-sarif` when code scanning is available;
5. make the gate job a required branch-protection check;
6. require CODEOWNERS review for policy, corpus, and gate paths.

GitHub code scanning supports third-party SARIF 2.1.0. Public repositories can use code scanning; private/internal availability depends on the repository's GitHub Code Security configuration.

## Pull-request comment

Generate Markdown and publish it through your CI platform's authenticated comment mechanism. Do not grant PermitDiff itself repository write credentials; report publication belongs in the CI adapter.

## Other policy engines

Keep adapters outside the core decision path:

```text
external policy/trace format -> deterministic normalization -> PermitDiff Policy + corpus
```

An adapter must document information loss. If the external system depends on state PermitDiff cannot model, materialize representative scenarios and label the result as sampled regression evidence.
