# Public Claude Code preapproval-projection validation pilot

This pilot validates PermitDiff against a public historical change to a real Claude Code project settings file. Its claim is deliberately narrower than full Claude effective authority: the executable model covers the checked-in `permissions.allow` preapproval projection under unchanged `dontAsk` and deny context.

## Frozen public source

- Repository: `SpearIT-LLC/project-framework`
- Path: `.claude/settings.local.json`
- Baseline commit: `28133b63a9a54621c8d7be879ba671daf8464c1c`
- Baseline blob: `87d28d71c3a8b65142e5e090e8deb42130fd3637`
- Candidate commit: `d8a47de7f5f96d501432a7f02c6909c667a5f31d`
- Candidate blob: `2e5f2bb998c7e5ed4d6394b8934144207546472d`
- Candidate commit message: `chore: settings — enable spearit-framework-dev plugin, allow git mv / web research`

The exact public source snapshots are committed as `source-baseline.json` and `source-candidate.json`. `source.json` records their immutable provenance, the pre-registered permission delta, and the non-permission root-key change that remains outside the normalization claim.

## External semantics used by the normalization

Claude Code documents that:

- allow rules let the specified tool run without manual approval;
- `defaultMode: dontAsk` denies tools that are not pre-approved;
- a bare rule such as `Bash` matches all uses of the Bash tool;
- exact `WebFetch(domain:HOST)` rules scope WebFetch preapproval to a hostname.

Official reference: <https://code.claude.com/docs/en/permissions>

Both source revisions use `dontAsk`. The candidate adds three allow entries:

```text
Bash(git mv *)
WebFetch(domain:www.anthropic.com)
WebSearch
```

Within the modeled `permissions.allow` preapproval projection, only two additions widen authority. `Bash(git mv *)` is redundant because the baseline already contains bare `Bash`, which covers every Bash command. The normalized PermitDiff policies therefore add only WebSearch and the scoped Anthropic WebFetch preapproval.

This de-noising is deliberate: a textual list diff reports three additions; the modeled preapproval projection reports two expansions.

The source revision also enables `spearit-framework-dev@dev-marketplace` under the root `enabledPlugins` object. That change is preserved in the frozen source and called out in `source.json`, but the pilot does **not** model capability changes introduced by plugin activation.

Claude Code's current documentation also states that domain-scoped WebFetch rules can affect sandbox network-domain policy. This pilot models the WebFetch **preapproval** effect only. It does not claim to quantify or waive the sandbox/network side effect.

## Pre-registered outcomes

| Scenario | Baseline | Candidate | Purpose |
|---|---|---|---|
| `existing-bash-git-mv` | `allow` | `allow` | Redundancy control for the newly listed scoped Bash rule. |
| `new-websearch` | `deny` | `allow` | Modeled project-level preapproval expansion. |
| `new-anthropic-webfetch` | `deny` | `allow` | Modeled domain-scoped WebFetch preapproval expansion. |
| `other-domain-webfetch` | `deny` | `deny` | Scope-control for WebFetch. |

Expected PermitDiff evidence for this projection:

- 2 observed privilege expansions;
- 2 new allows;
- 0 approval bypasses;
- 2 static potential authority expansions;
- 0 static unknowns;
- 0 uncovered candidate rules;
- strict gate result: BLOCK.

## Reproduce

```bash
permitdiff compare \
  validation/public-claude-permission-widening/baseline.yaml \
  validation/public-claude-permission-widening/candidate.yaml \
  validation/public-claude-permission-widening/corpus.jsonl \
  --gate validation/public-claude-permission-widening/gate.yaml \
  --format json
```

The executable contract is `tests/test_validation_pilots.py`.

## Claim boundary

This pilot models only the checked-in `permissions.allow` preapproval projection. It does not model the source's `enabledPlugins` change, plugin-provided capabilities, managed or user-level overrides, hooks, sandbox/network policy, version-specific built-in behavior, or unrelated unchanged deny rules outside the selected scenarios.

A PASS or waiver in this projection must not be interpreted as approval of those omitted surfaces. The historical pilot currently BLOCKs on the two modeled preapproval expansions.

It is a repository-local historical retrospective. It strengthens independent semantic validation but does **not** replace external-repository execution evidence for a release candidate.
