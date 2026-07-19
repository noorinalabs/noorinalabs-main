.PHONY: help setup-hooks lint format docs skeleton

help:
	@echo "Targets:"
	@echo "  setup-hooks                   Install pre-commit hooks (one-time per clone)"
	@echo "  lint                          Run ruff lint on .claude/hooks/"
	@echo "  format                        Run ruff format on .claude/hooks/"
	@echo "  docs                          Regenerate MS Office docs from their markdown sources"
	@echo "  skeleton                      Signatures-only skeleton of a subtree for a token-lean spawn brief"
	@echo "                                (DIR=dir INCLUDE=glob OUT=path)"

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

# ---- Lean-brief tooling (#1020) --------------------------------------------
#
# Pack a Tree-sitter-compressed *skeleton* of a code subtree (signatures kept,
# bodies stripped — roughly halving to two-thirds off raw token count) for a
# token-lean spawn brief. Paste the OUT file's contents into the brief instead
# of whole source files. The ontology already SELECTS which subtree matters
# (see /ontology-librarian); this COMPRESSES it — the two compose. See
# .claude/team/charter/agents/session-hygiene.md § Lean Section-Extract Briefs.
#
# Dependency: repomix, fetched on demand via `npx --yes repomix` (needs Node's
# npx on PATH; nothing is added to the repo). `--include` narrows to specific
# files/globs within DIR when the whole subtree is too broad.
DIR     ?= .
INCLUDE ?=
OUT     ?= /tmp/repomix-skeleton.xml

skeleton:
	@command -v npx >/dev/null 2>&1 || { echo "ERROR: npx not found (Node required for repomix)"; exit 1; }
	npx --yes repomix --compress --style xml --no-file-summary --no-directory-structure \
		$(if $(INCLUDE),--include "$(INCLUDE)") -o "$(OUT)" "$(DIR)"
	@echo ""
	@echo "Skeleton written to $(OUT) — paste its contents into the spawn brief instead of whole files."
