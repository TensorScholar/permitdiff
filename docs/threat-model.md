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
| Native adapter source files | Untrusted until validated | Format validation, bounded input size, duplicate-key rejection where applicable, source digests, explicit projection evidence. |
| MCP-style annotations | Untrusted hints | Cannot support an `allow` rule unless trusted metadata is explicitly required. |
| Waiver metadata | Administrative evidence | Exact evidence binding, mandatory reason, expiry; repository review remains external. |
| CI environment | Operationally trusted | PermitDiff does not protect a compromised runner or repository administrator. |

## Threats and controls

### Malformed or ambiguous policy

**Threat:** typos, unknown keys, duplicate IDs, implicit defaults, invalid predicates, or values that cannot be canonically serialized.

**Controls:** strict Pydantic schemas, duplicate checks, explicit API/kind fields, safe YAML loader, bounded canonical JSON validation, and validation commands.

### Native-adapter semantic collapse

**Threat:** an external syntax is normalized into a PermitDiff rule that looks equivalent but has additional source-system semantics, producing a misleading PASS or waiver scope.

**Controls:** adapters must document a bounded projection, reject changed unsupported semantics, expose omitted/ignored source surfaces in evidence, and avoid equivalence rules unless source semantics support them. For the Claude Code adapter, `WebFetch(domain:*)` is not collapsed into bare `WebFetch` because current Claude Code semantics differ at the sandbox-network layer. Exact domain rules are modeled only as WebFetch preapprovals, with the sandbox/network side effect explicitly outside the projection.

### Omitted native-source changes

**Threat:** a settings file changes outside the modeled projection while reviewers interpret PermitDiff output as a verdict on the whole source artifact.

**Controls:** source digests bind the exact inputs; adapter evidence records ignored root-key names and which ignored keys changed; documentation and report language define the projection. The Claude adapter surfaces non-`permissions` changes such as `enabledPlugins` but does not claim to assess plugin-provided capability changes. A waiver applies only to the normalized PermitDiff finding, never to omitted source-system semantics.

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

**Controls:** no wildcard waivers. Observed-transition waivers bind to scenario ID, exact effect transition, and action fingerprint. Static-authority waivers bind to finding kind and fingerprint plus exact baseline/candidate policy digests. Both require expiry and substantive reason; unused-waiver failures can detect stale approvals. A waiver for one evidence channel cannot suppress the other channel, and an adapter waiver cannot approve source semantics omitted by the adapter projection.

### Report tampering or confusion

**Threat:** reviewers compare the wrong artifacts or machine output is nondeterministic.

**Controls:** policy and corpus digests, native-source digests where applicable, per-action and per-finding fingerprints, stable serialization, deterministic sorting, explicit baseline/candidate metadata, and separate observed/static evidence channels.

### CI bypass

**Threat:** a privileged maintainer disables the workflow, changes gate thresholds, or merges without required checks.

**Controls:** outside PermitDiff. Use protected branches, CODEOWNERS for policy/gate paths, required checks, signed commits/releases, and auditable repository administration.

## Out of scope

PermitDiff does not provide authentication, runtime authorization, sandboxing, secret isolation, tool-server attestation, policy distribution, approval workflow, or tamper-proof storage. Its static analyzer and native adapters are deliberately bounded and are not proofs of exhaustive authorization safety. It cannot defend against a compromised CI runner or repository administrator.
