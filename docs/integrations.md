# Integrations

## GitHub Actions

`permitdiff init` includes a minimal workflow. For this repository, `.github/workflows/ci.yml` demonstrates a fuller matrix and artifact flow.

A robust integration should:

1. compare the merge-base policy and proposed policy over the same committed corpus;
2. write Markdown/JSON/SARIF before checking the exit code;
3. preserve reports as workflow artifacts;
4. upload SARIF with `github/codeql-action/upload-sarif` when code scanning is available;
5. make the gate job a required branch-protection check;
6. require CODEOWNERS review for policy, corpus, gate, and adapter configuration paths.

GitHub code scanning supports third-party SARIF 2.1.0. Public repositories can use code scanning; private/internal availability depends on the repository's GitHub Code Security configuration.

## Pull-request comment

Generate Markdown and publish it through your CI platform's authenticated comment mechanism. Do not grant PermitDiff itself repository write credentials; report publication belongs in the CI adapter.

## Native and external policy adapters

Keep adapters outside the core decision path:

```text
external policy/settings/trace format
        |
        v
bounded deterministic projection + evidence
        |
        v
PermitDiff Policy + review corpus
        |
        v
comparison + static authority analysis + release gate
```

An adapter is not allowed to hide information loss. It should:

- define the exact source-system surface it models;
- fail closed when a changed construct falls outside that surface and could invalidate the modeled claim;
- bind evidence to the exact native source artifacts with stable digests;
- surface ignored source regions and changed ignored regions without leaking unnecessary values;
- require explicit acknowledgement before continuing across a known projection gap that could otherwise be mistaken for a whole-source PASS;
- distinguish acknowledgement of projection scope from risk acceptance, waivers, or approval;
- distinguish normalized review metadata from raw source-system input fields;
- document source-system side effects that the normalized PermitDiff action model does not represent;
- keep waivers scoped to normalized findings rather than implying approval of omitted native semantics.

If the external system depends on state PermitDiff cannot model, materialize representative scenarios and label the result as sampled or projected regression evidence. Do not call a bounded projection a proof of full effective authority.

### Claude Code development adapter

`permitdiff claude compare` is the first built-in native projection. It currently supports explicit `permissions.defaultMode = "dontAsk"` pairs with unchanged `deny` and `ask` context. Bare-tool translation is intentionally limited to `Bash`, `PowerShell`, `WebFetch`, and `WebSearch`; other bare tools and unsupported scoped rules remain opaque and must remain unchanged. Exact `WebFetch(domain:HOST)` declarations are projected as preapprovals with an independent sandbox-gap control.

If non-`permissions` root settings differ, the command fails unless the reviewer explicitly supplies `--allow-ignored-root-changes`. Ignored root values are compared using canonical digests, while evidence exposes only key names and drift. If any exact WebFetch-domain declaration differs—even when preapproval-redundant beneath bare `WebFetch`—the command independently requires `--acknowledge-webfetch-sandbox-gap` because Claude Code domain rules can also affect sandbox network policy. These flags authorize analysis of the bounded projection only; they are not safety approvals and do not waive the omitted source-system semantics.

The evidence record includes source SHA-256 digests, translated/opaque/redundant allow rules, declared exact WebFetch domains, ignored root-key names, changed ignored root-key names, the two acknowledgement booleans, and the adapter claim boundary. Treat evidence files as review artifacts: native permission-rule text can be sensitive.

Current Claude Code documentation gives domain-scoped WebFetch rules sandbox-network effects in addition to WebFetch preapproval. The adapter models only the preapproval projection. It therefore does not treat `WebFetch(domain:*)` as equivalent to bare `WebFetch`, and a changed wildcard-domain rule fails closed.
