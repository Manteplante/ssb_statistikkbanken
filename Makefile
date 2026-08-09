SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help sync format lint typecheck test test-net check coverage kernel notebook fixtures clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t20

sync:  ## Create/update .venv from uv.lock
	uv sync --locked

format:  ## Auto-fix lint violations, then format
	uv run ruff check --fix . && uv run ruff format .

lint:  ## Lint and check formatting, writing nothing (what CI runs)
	uv run ruff check . && uv run ruff format --check .

typecheck:  ## Type-check src/
	uv run mypy src

test:  ## Offline suite against recorded fixtures (no network)
	uv run pytest

test-net:  ## Live smoke tests against SSB and KLASS (needs network)
	uv run pytest -m network

check: lint typecheck test  ## Everything CI runs, in CI's order

coverage:  ## Offline suite with an HTML report in htmlcov/
	uv run pytest --cov=ssb_statistikkbanken --cov-report=term-missing --cov-report=html

kernel:  ## Register this repo's venv as a Jupyter kernel (idempotent)
	uv run python -m ipykernel install --user --name ssb-statistikkbanken \
		--display-name "ssb-statistikkbanken (.venv)"

notebook: kernel  ## Scaffold a notebook in eda/ -- prompts for anything not given via name=/subdir=
	@name="$(name)"; subdir="$(subdir)"; \
	if [ -z "$$name" ]; then read -r -p "Notebook name: " name; fi; \
	if [ -z "$$name" ]; then echo "A notebook name is required."; exit 1; fi; \
	if [ -z "$$subdir" ]; then read -r -p "Subfolder in eda/ (blank to create it directly in eda/): " subdir; fi; \
	args=("$$name"); \
	if [ -n "$$subdir" ]; then args+=(--dir "$$subdir"); fi; \
	uv run python scripts/new_notebook.py "$${args[@]}"

fixtures:  ## Re-record tests/fixtures/**/*.json from the live APIs
	uv run python tests/fixtures/refresh.py

clean:  ## Remove caches and build artefacts (keeps .venv and uv.lock)
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage dist build
	find . -path ./.venv -prune -o -name __pycache__ -type d -exec rm -rf {} +
