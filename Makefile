.PHONY: help setup-hooks lint format docs

help:
	@echo "Targets:"
	@echo "  setup-hooks                   Install pre-commit hooks (one-time per clone)"
	@echo "  lint                          Run ruff lint on .claude/hooks/"
	@echo "  format                        Run ruff format on .claude/hooks/"
	@echo "  docs                          Regenerate MS Office docs from their markdown sources"

setup-hooks:
	@command -v pre-commit >/dev/null 2>&1 || { \
		echo "pre-commit not found. Install with: pip install pre-commit  (or: brew install pre-commit)"; \
		exit 1; \
	}
	pre-commit install

# NOTE (main#939): the `setup-ontology-merge-driver` target was removed. main no
# longer commits its structural index (see .gitignore / ontology/README.md
# § Structural layer), so there is nothing here to merge and main no longer
# registers the driver. GitHub's server-side merge never ran that driver anyway,
# which is why committing the index made every concurrent PR conflict. The
# `.claude/lib/ontology_gen/merge_driver.py` MODULE stays: not-yet-migrated child
# repos resolve it against this repo's `.claude/lib` (#854), so it is retained until the
# terminal child-rollout step deletes it. See docs/devops/ontology-structural.md.

lint:
	python3 -m ruff check .claude/hooks/ .claude/lib/

format:
	python3 -m ruff format .claude/hooks/ .claude/lib/

# Regenerate the Microsoft Office docs (docs/office/) from their markdown
# sources. Markdown is the source of truth; the binaries are artifacts. See
# docs/office/README.md.
docs:
	scripts/gen-office.sh
