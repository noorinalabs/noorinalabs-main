.PHONY: help setup-hooks lint format

help:
	@echo "Targets:"
	@echo "  setup-hooks   Install pre-commit hooks (one-time per clone)"
	@echo "  lint          Run ruff lint on .claude/hooks/"
	@echo "  format        Run ruff format on .claude/hooks/"

setup-hooks:
	@command -v pre-commit >/dev/null 2>&1 || { \
		echo "pre-commit not found. Install with: pip install pre-commit  (or: brew install pre-commit)"; \
		exit 1; \
	}
	pre-commit install

lint:
	python3 -m ruff check .claude/hooks/

format:
	python3 -m ruff format .claude/hooks/
