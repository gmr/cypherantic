all: lint test

lint:
	uv run pre-commit run --all-files

typecheck:
	uv run mypy example.py src tests

test: ensure-running
	uv run coverage run -m pytest
	uv run coverage report

format:
	- uv run ruff check --fix src tests
	- uv run ruff format example.py src tests

clean:
	- docker compose down --remove-orphans --volumes
	- rm -fr build dist .mypy_cache .pytest_cache .ruff_cache
	- rm -f .coverage .env

ensure-running:
	./bootstrap

.PHONY: all ensure-running format lint test
