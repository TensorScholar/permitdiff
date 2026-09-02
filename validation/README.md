# Validation evidence

This directory contains reproducible validation pilots that test narrowly stated
PermitDiff claims against frozen evidence from systems outside PermitDiff's own
example corpus.

A pilot must:

- identify immutable source repository revisions;
- pre-register the exact ground-truth claim before asserting PermitDiff output;
- document every normalization assumption and known information loss;
- include positive and negative controls where the claim permits them;
- expose an executable regression test;
- state what the evidence does **not** establish.

Current pilots:

- [`agentguard-approval-exception`](agentguard-approval-exception/) — historical
  AgentGuard change where a scoped `run_* + shell_execution` exception introduced
  an approval-to-allow path while nonmatching and unrelated actions remained
  constrained.

These repository-local retrospectives are not substitutes for the separate
release-readiness requirement to run a release candidate successfully in an
external repository.
