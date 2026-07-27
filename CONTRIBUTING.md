# Contributing

PermitDiff accepts focused changes that strengthen deterministic permission review without expanding into an agent framework or runtime authorization service.

## Before opening a pull request

1. Open an issue for schema or semantic changes.
2. Add or update an ADR when the change alters a security invariant or public behavior.
3. Add tests for success, failure, boundary, and trust cases.
4. Update schemas and documentation.
5. Run `make check`.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pre-commit install
make check
```

## Pull-request requirements

- one coherent change;
- no unrelated formatting churn;
- public behavior documented;
- branch-aware coverage remains at least 90%;
- strict mypy and Ruff pass;
- no high-severity dependency audit finding without documented acceptance;
- generated schemas are current;
- commits contain no secrets or private production data.

## Design constraints

- no arbitrary code execution in policies;
- no network I/O in the engine or gate;
- no implicit trust of tool annotations;
- no wildcard or non-expiring waivers;
- no probabilistic decision logic;
- no distributed infrastructure without measured need.
