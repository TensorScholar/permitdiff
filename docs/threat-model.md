# Threat model

## Assets

- integrity of the release verdict;
- traceability of compared policy and corpus artifacts;
- visibility of privilege expansions and approval bypasses;
- integrity and expiry of waivers;
- CI availability within documented resource bounds.

## Trust boundaries

| Input | Default trust | Treatment |
|---|---|---|
| Policy/gate YAML committed by maintainers | Untrusted until validated | Safe YAML parsing, strict schemas, size limits. |
| Scenario JSONL | Untrusted until validated | Streaming parse, line-aware failures, bounded size/count/depth. |
| MCP-style annotations | Untrusted hints | Cannot support an `allow` rule unless trusted metadata is explicitly required. |
| Waiver metadata | Administrative evidence | Exact transition binding, mandatory reason, expiry; repository review remains external. |
| CI environment | Operationally trusted | PermitDiff does not protect a compromised runner or repository administrator. |

## Threats and controls

### Malformed or ambiguous policy

**Threat:** typos, unknown keys, duplicate IDs, implicit defaults, invalid predicates.

**Controls:** strict Pydantic schemas, duplicate checks, explicit API/kind fields, safe YAML loader, validation commands.

### Untrusted annotation escalation

**Threat:** a tool server declares itself read-only or non-destructive to gain automatic access.

**Controls:** `allow` rules that depend on risk annotations must require `security_metadata_trusted: true`. Corpus authors must establish trust out of band.

### Corpus resource exhaustion

**Threat:** very large files, excessive scenario count, deeply nested arguments, or non-finite values consume CI resources or break canonicalization.

**Controls:** 50 MB file limit, 100,000-case limit, maximum JSON depth, finite-number validation, line streaming.

### Waiver abuse

**Threat:** a broad or permanent waiver masks unrelated future permission expansions.

**Controls:** exact scenario/effect binding, expiry, optional issue link, and unused-waiver failures. There is no wildcard waiver.

### Report tampering or confusion

**Threat:** reviewers compare the wrong artifacts or machine output is nondeterministic.

**Controls:** policy and corpus digests, per-action fingerprints, stable schema versions, deterministic sorting, explicit baseline/candidate metadata.

### CI bypass

**Threat:** a privileged maintainer disables the workflow, changes gate thresholds, or merges without required checks.

**Controls:** outside PermitDiff. Use protected branches, CODEOWNERS for policy/gate paths, required checks, signed commits/releases, and auditable repository administration.

## Out of scope

PermitDiff does not provide authentication, runtime authorization, sandboxing, secret isolation, tool-server attestation, policy distribution, approval workflow, or tamper-proof storage. It cannot defend against a compromised CI runner or repository administrator.
