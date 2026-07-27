.PHONY: install format lint type test schemas build audit check demo benchmark release-check clean

install:
	python -m pip install -e '.[dev]'

format:
	ruff format .
	ruff check --fix .

lint:
	ruff format --check .
	ruff check .

type:
	mypy src

test:
	pytest

schemas:
	python scripts/generate_schemas.py --check

build:
	python -m build
	python -m twine check dist/*

audit:
	pip-audit

check: lint type test schemas build

demo:
	bash scripts/demo.sh

benchmark:
	python benchmarks/compare_benchmark.py --scenarios 20000

release-check:
	python scripts/check_release.py --tag "v$$(python -c 'from permitdiff import __version__; print(__version__)')"

clean:
	rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache build dist htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
