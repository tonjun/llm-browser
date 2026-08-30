.PHONY: help install run test lint format clean

help:
	@echo "Available targets:"
	@echo "  install  - Sync dependencies with uv"
	@echo "  run      - Run the llm-browser CLI (use ARGS=... to pass arguments)"
	@echo "  test     - Run the test suite with pytest"
	@echo "  lint     - Run ruff checks"
	@echo "  format   - Format code with ruff"
	@echo "  clean    - Remove caches and build artifacts"

install:
	uv sync

run:
	uv run llm-browser $(ARGS)

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

clean:
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +
	rm -rf .pytest_cache dist build *.egg-info
