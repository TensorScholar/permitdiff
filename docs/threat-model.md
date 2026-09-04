# Threat model

## Assets

- integrity of the release verdict;
- traceability of compared policy and corpus artifacts;
- visibility of observed privilege expansions, approval bypasses, and policy-level authority findings;
- visibility of information intentionally omitted by native-source projections;
- integrity and expiry of waivers;
- CI availability within documented resource bounds.

## Trust boundaries

| Input | Default trust | Treatment |
|---|---|---|
| Policy/gate YAML committed by maintainers | Untrusted until validated | Safe YAML parsing, strict schemas, size limits. |
| Scenario JSONL | Untrusted until validated | Streaming parse, line-aware failures, bounded size/count/depth. |
| Git baseline ref/object database | Untrusted until resolved and validated | Restricted ref/path syntax, exact commit/blob resolution, blob type/size checks, raw source digest, normal policy validation. |
| Native adapter source files | Untrusted until validated | Format validation, bounded input size, duplicate-key rejection where applicable, source digests, explicit projection evidence. |
| MCP-style annotations | Untrusted hints | Cannot support an `allow` rule unless trusted metadata is explicitly required. |
| Waiver metadata | Administrative evidence | Exact evidence binding, mandatory reason, expiry; repository review remains external. |
| CI environment | Operationally trusted | PermitDiff does not protect a compromised runner or repository administrator. |

## Threats and controls

### Malformed or ambiguous policy

**Threat:** typos, unknown keys, duplicate IDs, implicit defaults, invalid predicates, or values that cannot be canonically serialized.

**Controls:** strict Pydantic schemas, duplicate checks, explicit API/kind fields, safe YAML loader, bounded canonical JSON validation, and validation commands.

### Git baseline ref confusion or source substitution

**Threat:** a CI job compares against a moving, attacker-chosen, ambiguous, or incorrectly materialized baseline and reviewers believe it represents the intended protected base branch.

**Controls:** `--baseline-ref` accepts a deliberately narrow ref-like syntax rather than arbitrary revision expressions; repository-relative paths reject traversal and control characters; PermitDiff resolves the requested ref once to an exact commit, resolves the policy to an exact Git blob, verifies object type and size before reading, and emits requested ref, resolved commit, path, Git object ID, and raw SHA-256 as provenance. The baseline is read with `git cat-file` and is not checked out or executed. CI adapters should derive the requested ref from trusted base-branch metadata and preserve the evidence. The semantic comparison independently binds the validated policy by canonical policy digest.

This does not make an untrusted local Git object database trustworthy. A compromised runner, malicious repository administrator, or workflow that fetches the wrong remote/ref can still provide the wrong source. PermitDiff makes the selected source explicit and immutable after resolution; selecting the correct trusted ref remains an integration responsibility.

### Native-adapter semantic collapse

**Threat:** an external syntax is normalized into a PermitDiff rule that looks equivalent but has additional source-system semantics, producing a misleading PASS or waiver scope.

**Controls:** adapters must document a bounded projection, reject changed unsupported semantics, expose omitted/ignored source surfaces in evidence, and avoid equivalence rules unless source semantics support them. For the Claude Code adapter, `WebFetch(domain:*)` is not collapsed into bare `WebFetch` because current Claude Code semantics differ at the sandbox-network layer. Exact domain-rule changes require explicit sandbox-gap acknowledgement before the preapproval projection can run; the acknowledgement is recorded as evidence and does not waive the omitted sandbox semantics.

### Omitted native-source changes

**Threat:** a settings file changes outside the modeled projection while reviewers interpret PermitDiff output as a verdict on the whole source artifact.

**Controls:** source digests bind the exact inputs; adapter evidence records ignored root-key names and which ignored keys changed; documentation and report language define the projection. The Claude adapter fails on changed non-`permissions` root surfaces unless the reviewer explicitly acknowledges the ignored-root drift. That acknowledgement is recorded but does not approve the ignored change. The adapter surfaces changes such as `enabledPlugins` without claiming to assess plugin-provided capability changes. A waiver applies only to the normalized PermitDiff finding, never to omitted source-system semantics.

### Untrusted annotation escalation

**Threat:** a tool server declares itself read-only or non-destructive to gain automatic access.

**Controls:** `allow` rules that depend on risk annotations must require `security_metadata_trusted: true`. Corpus authors must establish trust out of band.

### Corpus resource exhaustion

**Threat:** very large files, excessive scenario count, deeply nested arguments, non-finite values, or non-canonicalizable values consume CI resources or break evidence hashing.

**Controls:** 50 MB file limit, 100,000-case limit, maximum JSON depth, canonical-value validation, finite-number validation, and line streaming.

### Scenario blind spots

**Threat:** the supplied corpus omits a permission-relevant request, so a policy change has no observed transition even though effective authority changed.

**Controls:** the scenario report is explicitly labeled observed evidence, not exhaustive policy coverage. PermitDiff also performs bounded static authority analysis over rule effects, supported match-set containment, defaults, and precedence. Unsupported or ambiguous containment becomes `unknown` and the strict gate fails closed.

### Waiver abuse or replay

**Threat:** a broad, stale, or replayed waiver masks unrelated future permission expansions.

**Controls:** no wildcard waivers. Observed-transition waivers bind to scenario ID, exact effect transition, action fingerprint, and exact baseline/candidate policy digests. Static-authority waivers bind to finding kind and fingerprint plus exact baseline/candidate policy digests. Both require expiry and substantive reason; unused-waiver failures can detect stale approvals. A waiver for one evidence channel cannot suppress the other channel, and an adapter waiver cannot approve source semantics omitted by the adapter projection. Projection acknowledgement flags are not waivers.

### Report tampering or confusion

**Threat:** reviewers compare the wrong artifacts or machine output is nondeterministic.

**Controls:** policy and corpus digests, Git commit/blob/raw-source evidence where applicable, native-source digests where applicable, per-action and per-finding fingerprints, stable serialization, deterministic sorting, explicit baseline/candidate metadata, projection acknowledgement evidence, and separate observed/static evidence channels.

### CI bypass

**Threat:** a privileged maintainer disables the workflow, changes gate thresholds, or merges without required checks.

**Controls:** outside PermitDiff. Use protected branches, CODEOWNERS for policy/gate paths, required checks, signed commits/releases, and auditable repository administration.

## Out of scope

PermitDiff does not provide authentication, runtime authorization, sandboxing, secret isolation, tool-server attestation, policy distribution, approval workflow, or tamper-proof storage. Its static analyzer and native adapters are deliberately bounded and are not proofs of exhaustive authorization safety. It cannot defend against a compromised CI runner, local Git object database controlled by an attacker with runner privileges, or repository administrator.
