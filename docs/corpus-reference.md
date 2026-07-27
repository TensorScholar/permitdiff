# Corpus reference

A corpus is UTF-8 JSON Lines. Each non-blank line is one `Scenario`.

## Scenario fields

| Field | Required | Description |
|---|---:|---|
| `id` | yes | Unique stable case ID. |
| `action` | yes | Normalized action request. |
| `risk` | no | `low`, `medium`, `high`, or `critical`; defaults to `medium`. |
| `description` | no | Why the case exists and what boundary it represents. |
| `owner` | no | Team or person accountable for the case. |
| `tags` | no | Sorted, de-duplicated review labels. |

## Action fields

`principal`, `agent`, and `tool` are required. `request_id`, `arguments`, `annotations`, `context`, and `requested_at` are optional.

`request_id` and `requested_at` are excluded from action fingerprints and the normalized corpus digest. They are not used by the policy language.

`Scenario.risk` controls review severity. Policy `risks` matching uses trusted `action.context.risk` when present, otherwise PermitDiff derives a conservative risk from trusted annotations. This separation prevents a reporting label from silently changing authorization semantics.

## Corpus design guidance

Include at least:

- one case selecting every candidate rule;
- default-effect cases;
- values immediately below, at, and above thresholds;
- trusted and untrusted metadata variants;
- destructive and read-only variants;
- historical incidents and denied abuse attempts;
- principal, agent, environment, and source boundaries.

Prefer explicit cases over generated noise. Every scenario should be reviewable and have a stable reason to exist.
