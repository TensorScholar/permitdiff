"""Native permission-source adapters.

Adapters are deliberately conservative: unsupported source semantics are rejected or
carried as explicit evidence rather than silently approximated.
"""

from permitdiff.adapters.claude_code import (
    ClaudePreapprovalEvidence,
    ClaudePreapprovalPair,
    normalize_claude_preapproval_pair,
)

__all__ = [
    "ClaudePreapprovalEvidence",
    "ClaudePreapprovalPair",
    "normalize_claude_preapproval_pair",
]
