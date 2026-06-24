.PHONY: help setup-hooks setup-ontology-merge-driver lint format docs

help:
	@echo "Targets:"
	@echo "  setup-hooks                   Install pre-commit hooks (one-time per clone)"
	@echo "  setup-ontology-merge-driver   Register the code-graph union merge-driver (one-time per clone)"
	@echo "  lint                          Run ruff lint on .claude/hooks/"
	@echo "  format                        Run ruff format on .claude/hooks/"
	@echo "  docs                          Regenerate MS Office docs from their markdown sources"

setup-hooks:
	@command -v pre-commit >/dev/null 2>&1 || { \
		echo "pre-commit not found. Install with: pip install pre-commit  (or: brew install pre-commit)"; \
		exit 1; \
	}
	pre-commit install

# Register the union merge-driver named in .gitattributes for the structural
# ontology graph artifacts (ontology/structural/{code-graph,cross-repo-graph}.json).
# .gitattributes only names `merge=ontology-codegraph`; the driver COMMAND is
# per-clone local git config (it cannot be committed), so run this once per clone
# (main#856, #820 C×T2). Without it git falls back to the default text merge and
# the sorted JSON spuriously conflicts on parallel regenerations.
setup-ontology-merge-driver:
	git config merge.ontology-codegraph.name 'ontology code-graph union merge'
	git config merge.ontology-codegraph.driver \
		'python3 .claude/lib/ontology_gen/merge_driver.py %O %A %B %P'
	@echo "Registered merge driver 'ontology-codegraph' (see .gitattributes)."

lint:
	python3 -m ruff check .claude/hooks/ .claude/lib/

format:
	python3 -m ruff format .claude/hooks/ .claude/lib/

# Regenerate the Microsoft Office docs (docs/office/) from their markdown
# sources. Markdown is the source of truth; the binaries are artifacts. See
# docs/office/README.md.
docs:
	scripts/gen-office.sh
