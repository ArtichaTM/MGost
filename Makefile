.PHONY: verify test merge-main

# Runs every CI check locally; the steps live in scripts/verify.py.
verify:
	@uv run scripts/verify.py

# Runs the test suite.
test:
	uv run --locked pytest

# Fast-forwards main to dev, runs `make verify` on it and pushes; rolls back on failure.
merge-main:
	bash scripts/merge-main.sh
