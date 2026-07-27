"""PermitDiff public API."""

from permitdiff._version import __version__
from permitdiff.analysis import ComparisonReport, compare_policies
from permitdiff.corpus import load_corpus
from permitdiff.engine import PolicyEngine
from permitdiff.gate import GateConfig, GateResult, evaluate_gate, strict_gate
from permitdiff.models import ActionRequest, DecisionEffect, RiskLevel, Scenario
from permitdiff.policy import PolicyDocument

__all__ = [
    "__version__",
    "ActionRequest",
    "ComparisonReport",
    "DecisionEffect",
    "GateConfig",
    "GateResult",
    "PolicyDocument",
    "PolicyEngine",
    "RiskLevel",
    "Scenario",
    "compare_policies",
    "evaluate_gate",
    "load_corpus",
    "strict_gate",
]

