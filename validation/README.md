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

Repository-local retrospectives do not replace the separate release-readiness requirement to run a PermitDiff release candidate successfully in an external repository.
