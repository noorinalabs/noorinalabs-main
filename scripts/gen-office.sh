#!/bin/sh
# gen-office.sh — regenerate Microsoft Office documents from their markdown
# sources.
#
# Markdown is the SINGLE SOURCE OF TRUTH; the office binaries under each
# manifest entry's `target` are GENERATED artifacts and must never be
# hand-edited. Edit the markdown, then rerun this script (or `make docs`).
#
# Manifest:  docs/office/office-docs.json  (JSON so it needs no PyYAML; it is
#            also validated by the docs.yml config-lint JSON-parse gate).
# Engine:    pandoc, resolved in this order:
#              1. $PANDOC, if set
#              2. `pandoc` on PATH
#              3. the pandoc binary bundled by the pip `pypandoc` package
#                 (`pip install pypandoc-binary`) — so `make docs` works with
#                 no system package install.
#
# Reproducibility: each document's embedded OOXML timestamp is pinned to the
# source file's last git commit time via SOURCE_DATE_EPOCH, so regenerating
# from an unchanged source on the same pandoc version yields byte-identical
# output (the precondition a future sync-drift CI check would rely on).
#
# Usage:  scripts/gen-office.sh
#         PANDOC=/path/to/pandoc scripts/gen-office.sh
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

MANIFEST="docs/office/office-docs.json"

# --- resolve a pandoc executable ------------------------------------------
if [ -n "${PANDOC:-}" ]; then
  :
elif command -v pandoc >/dev/null 2>&1; then
  PANDOC="$(command -v pandoc)"
else
  PANDOC="$(python3 -c 'import pypandoc; print(pypandoc.get_pandoc_path())' 2>/dev/null || true)"
fi

if [ -z "${PANDOC:-}" ] || [ ! -x "$PANDOC" ]; then
  echo "error: pandoc not found. Install one of:" >&2
  echo "    apt install pandoc            # Debian / Ubuntu / WSL" >&2
  echo "    brew install pandoc           # macOS" >&2
  echo "    pip install pypandoc-binary   # bundled pandoc, no system package" >&2
  exit 1
fi

if [ ! -f "$MANIFEST" ]; then
  echo "error: manifest not found: $MANIFEST" >&2
  exit 1
fi

# --- read the manifest into TAB-separated source/target/format tuples ------
# A real JSON parse (python3 stdlib is always present) rather than a line-scan,
# so reordering keys or adding fields can't break it. Entries with
# "enabled": false are skipped (used to register a doc whose markdown source
# has not landed yet, e.g. the #766 lifecycle doc).
TUPLES="$(python3 - "$MANIFEST" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for doc in data.get("documents", []):
    if not doc.get("enabled", True):
        continue
    print(f"{doc['source']}\t{doc['target']}\t{doc.get('format', 'docx')}")
PY
)"

if [ -z "$TUPLES" ]; then
  echo "no enabled documents in $MANIFEST — nothing to generate."
  exit 0
fi

# Drive the loop from a temp file (not a pipe) so `set -e`/`exit` act on the
# main shell, not a pipe subshell.
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
printf '%s\n' "$TUPLES" > "$TMP"

TAB="$(printf '\t')"
while IFS="$TAB" read -r src tgt fmt; do
  [ -n "$src" ] || continue
  if [ ! -f "$src" ]; then
    echo "error: source markdown not found: $src" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$tgt")"

  # Pin the embedded timestamp to the source's last commit for reproducibility.
  SOURCE_DATE_EPOCH="$(git log -1 --format=%ct -- "$src" 2>/dev/null || true)"
  [ -n "$SOURCE_DATE_EPOCH" ] || SOURCE_DATE_EPOCH=0
  export SOURCE_DATE_EPOCH

  echo "  $src -> $tgt ($fmt)"
  case "$fmt" in
    docx | pptx)
      "$PANDOC" --from gfm --to "$fmt" --output "$tgt" "$src"
      ;;
    *)
      echo "error: unsupported format '$fmt' for $src" >&2
      echo "       docx and pptx are produced by pandoc; xlsx (tabular data)" >&2
      echo "       uses openpyxl — see docs/office/README.md." >&2
      exit 1
      ;;
  esac
done < "$TMP"

echo "office documents regenerated from markdown."
