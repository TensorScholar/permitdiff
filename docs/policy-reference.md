# Policy reference

## Document fields

| Field | Required | Description |
|---|---:|---|
| `api_version` | yes | `permitdiff.dev/v1alpha1` |
| `kind` | yes | `Policy` |
| `metadata.name` | yes | Stable policy name. |
| `metadata.version` | yes | Human review version. |
| `metadata.description` | no | Scope and owner context. |
| `default_effect` | no | Defaults to `deny`. |
| `rules` | yes | Ordered first-match rules with unique IDs. |

## Effects

`deny`, `require_approval`, and `allow`.

## Match fields

Glob-list dimensions: `tools`, `principals`, `agents`, `environments`, and `sources`. Empty risk lists do not constrain risk. Boolean fields can constrain `security_metadata_trusted`, `read_only`, `destructive`, `idempotent`, and `open_world`.

## Argument predicates

| Operator | Value | Behavior |
|---|---|---|
| `equals`, `not_equals` | any JSON scalar/container | Equality comparison. |
| `in`, `not_in` | list | Membership comparison. |
| `contains` | scalar | Substring, list membership, or mapping-key containment. |
| `matches` | glob string or list | `fnmatch` glob match against a string value. |
| `exists` | boolean | Whether a dotted path resolves. |
| `less_than`, `less_than_or_equal` | comparable value | Ordered comparison; incompatible types fail the predicate. |
| `greater_than`, `greater_than_or_equal` | comparable value | Ordered comparison; incompatible types fail the predicate. |

Dotted paths navigate mappings only, for example `payment.amount`. Missing values fail all predicates except `exists: false`.

## Trust invariant

Any `allow` rule that constrains annotation-derived fields (`read_only`, `destructive`, `idempotent`, `open_world`) must also specify `security_metadata_trusted: true`. PermitDiff rejects policies that violate this invariant.
