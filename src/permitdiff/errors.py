"""Domain-specific exceptions."""


class PermitDiffError(Exception):
    """Base exception for PermitDiff."""


class PolicyLoadError(PermitDiffError):
    """Raised when a policy cannot be loaded or validated."""


class CorpusLoadError(PermitDiffError):
    """Raised when a scenario corpus cannot be loaded or validated."""


class GateLoadError(PermitDiffError):
    """Raised when a release gate cannot be loaded or validated."""
