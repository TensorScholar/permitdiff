# Gate reference

## Thresholds

| Field | Default | Meaning |
|---|---:|---|
| `max_privilege_expansions` | `0` | Maximum unwaived transitions to a more permissive effect. |
| `max_new_allows` | `0` | Maximum unwaived transitions from non-allow to allow. |
| `max_approval_bypasses` | `0` | Maximum unwaived `require_approval → allow` transitions. |
| `max_uncovered_candidate_rules` | `0` | Maximum candidate rules with no observed first-match hit; `null` disables. |
| `forbid_default_effect_relaxation` | `true` | Fail whenever the candidate default is more permissive, even if the current corpus has no default hit. |
| `fail_on_removed_rules` | `false` | Fail on any removed rule ID. |
| `fail_on_unused_waivers` | `false` | Fail when an active waiver matches no observed expansion. |

## Waivers

An observed-transition waiver requires a unique ID, scenario ID, baseline effect, candidate effect, action fingerprint, baseline policy digest, candidate policy digest, meaningful reason, and expiry date. A static-authority waiver requires a unique ID, finding kind, finding fingerprint, baseline policy digest, candidate policy digest, meaningful reason, and expiry date. `issue` accepts an HTTP(S) URL. Transition waivers without both policy digests fail validation and never match.

Expiry uses UTC calendar dates. A waiver is active through its `expires_on` date and expired the following day.
