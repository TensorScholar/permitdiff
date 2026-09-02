# Public Claude Code permission-widening validation pilot

This pilot validates PermitDiff against a public historical change to a real Claude Code project permission file.

## Frozen public source

- Repository: `SpearIT-LLC/project-framework`
- Path: `.claude/settings.local.json`
- Baseline commit: `28133b63a9a54621c8d7be879ba671daf8464c1c`
- Baseline blob: `87d28d71c3a8b65142e5e090e8deb42130fd3637`
- Candidate commit: `d8a47de7f5f96d501432a7f02c6909c667a5f31d`
- Candidate blob: `2e5f2bb998c7e5ed4d6394b8934144207546472d`
- Candidate commit message: `chore: settings — enable spearit-framework-dev plugin, allow git mv / web research`

The exact public source snapshots are committed as `source-baseline.json` and `source-candidate.json`. `source.json` records their immutable provenance and the pre-registered delta.

## External semantics used by the normalization

Claude Code documents that:

- allow rules let the specified tool run without manual approval;
- `defaultMode: dontAsk` denies tools that are not pre-approved;
- a bare rule such as `Bash` matches all uses of the Bash tool.

Official reference: <https://code.claude.com/docs/en/permissions>

Both source revisions use `dontAsk`. The candidate adds three allow entries:

```text
Bash(git mv *)
WebFetch(domain:www.anthropic.com)
WebSearch
```

Only two increase the project-level permission surface. `Bash(git mv *)` is redundant because the baseline already contains bare `Bash`, which already covers every Bash command. The normalized PermitDiff policies therefore add only WebSearch and the scoped Anthropic WebFetch grant.

This de-noising is deliberate: a textual list diff would report three additions; the permission-semantic projection reports two authority expansions.

## Pre-registered outcomes

| Scenario | Baseline | Candidate | Purpose |
|---|---|---|---|
| `existing-bash-git-mv` | `allow` | `allow` | Redundancy control for the newly listed scoped Bash rule. |
| `new-websearch` | `deny` | `allow` | True project-level permission expansion. |
| `new-anthropic-webfetch` | `deny` | `allow` | True domain-scoped permission expansion. |
| `other-domain-webfetch` | `deny` | `deny` | Scope-control for WebFetch. |

Expected PermitDiff evidence:

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

This pilot models the checked-in project permission layer, not every effective Claude Code control. Managed or user-level overrides, hooks, sandbox policy, version-specific built-in behavior, and unchanged deny rules outside the selected scenarios are not modeled.

It is a repository-local historical retrospective. It strengthens independent semantic validation but does **not** satisfy the separate release-readiness requirement that a PermitDiff release candidate execute successfully inside an external repository.
