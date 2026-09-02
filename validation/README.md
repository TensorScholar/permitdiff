# Validation evidence

This directory contains reproducible validation pilots for narrowly stated PermitDiff claims against frozen, independently inspectable external evidence.

A pilot must:

- identify immutable public source revisions and source blob hashes;
- freeze the relevant source artifacts in the pilot when their license and size permit it;
- pre-register the exact source delta before asserting PermitDiff output;
- document normalization assumptions and information loss;
- include positive and negative controls;
- expose an executable regression test;
- state what the evidence does **not** establish.

Current pilots:

- [`public-claude-permission-widening`](public-claude-permission-widening/) — a public Claude Code project-permission change that adds web pre-approvals under `dontAsk`, while a newly added scoped Bash rule is correctly treated as redundant because broad `Bash` access already existed.

Repository-local retrospectives are complemented by `.github/workflows/external-validation.yml`, which builds the wheel under test and executes it from the root of the pinned public repository used by the current pilot. That workflow verifies external commit/blob identity, keeps the external checkout clean, and uploads machine-readable execution evidence.

External-workspace validation is evidence of package execution and bounded semantic compatibility. It is not third-party adoption or a claim that PermitDiff models every permission system.
