.PHONY: clean lint format lint-format type test

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
	rm -rf .pytest_cache .uv_cache .coverage .ruff_cache

lint:
	uvx ruff check .

format:
	uvx ruff format .

lint-format:
	uvx ruff check . --fix
	uvx ruff format .

test:
	uv run pytest

type:
	uvx ty check .

