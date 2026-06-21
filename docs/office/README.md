# Generated Microsoft Office documents

This directory holds **generated** Microsoft Office files (`.docx`, and in
future `.pptx` / `.xlsx`). They are build artifacts, not authored documents.

> **Markdown is the single source of truth.** The binaries here are produced
> from their markdown sources by [`scripts/gen-office.sh`](../../scripts/gen-office.sh).
> Never hand-edit a file in this directory — your change would be silently
> overwritten on the next regeneration. Edit the markdown source instead, then
> rerun the generator.

## Convention

| Thing | Where |
|-------|-------|
| Markdown sources | wherever they naturally live (`docs/*.md`, `ontology/*.md`, …) |
| Generated office binaries | `docs/office/<name>.<ext>` |
| Source → target mapping | [`docs/office/office-docs.json`](office-docs.json) (the manifest) |

The manifest is the one place that records which markdown renders to which
office file and in which format. To add a document, add an entry to the
manifest and run the generator — do not drop a binary here by hand.

## Regenerate

```sh
make docs                 # regenerate every enabled doc in the manifest
scripts/gen-office.sh     # same thing, without make
```

The generator needs `pandoc`. It is resolved from `$PANDOC`, then from
`pandoc` on `PATH`, then from the pip-bundled binary (`pip install
pypandoc-binary`) — so `make docs` works even without a system `pandoc`. See
the **Document generation** section of [`../TOOLCHAIN.md`](../TOOLCHAIN.md) for
install options.

## Formats

- **`.docx` (Word)** — `pandoc --from gfm --to docx`. Implemented.
- **`.pptx` (PowerPoint)** — `pandoc --from gfm --to pptx` (markdown headings
  become slides). The generator already routes `pptx` through pandoc; add a
  manifest entry with `"format": "pptx"` when a deck source exists. For
  fine-grained slide control, `python-pptx` is the escape hatch.
- **`.xlsx` (Excel)** — spreadsheets are tabular data, not prose, so pandoc is
  the wrong tool. Generate these with `openpyxl` from a structured source
  (CSV / JSON / a data module). Wire it as a separate manifest format when a
  first spreadsheet source exists.

## Reproducibility

Each document's embedded OOXML timestamp is pinned to a **fixed project epoch**
(`SOURCE_DATE_EPOCH=1735689600`, 2025-01-01), so regenerating on the same
`pandoc` version produces byte-identical output. The epoch is deliberately a
fixed constant rather than the source's git commit time: squash-merge and rebase
re-time commits, so a commit-time epoch would change the bytes and turn the drift
gate red on `main` after any source edit (#792).

### Drift gate (#781)

The **`Office docs drift gate`** CI job (`.github/workflows/docs.yml`)
regenerates every enabled manifest entry and fails the build if a committed
binary differs from its markdown source — catching a source edited without
`make docs`, or a hand-edited binary. It is mirrored at pre-push by the
`office-drift` pre-commit hook, and the `office-drift` kind is classified by
the [`pre_commit_ci_sync.py`](../../.claude/lib/pre_commit_ci_sync.py) drift gate
so the CI⇄local mirror is enforced (#684).

**Pandoc version pin.** Because OOXML output bytes differ across pandoc
versions, the gate is only deterministic if local and CI use the *same* pandoc.
Both are pinned to the official **pandoc 3.9** bundled by **`pypandoc-binary==1.17`**
(the binary `gen-office.sh` resolves as its no-system-package fallback). This pin
sits alongside the other tool pins (ruff `0.15.11`, actionlint `1.7.12`, cspell
`8.4.0`); bump all three of CI (`docs.yml`), the pre-commit note, and this line
together, and regenerate + commit the binaries in the same change.
