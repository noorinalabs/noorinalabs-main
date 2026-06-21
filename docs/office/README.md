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

Each document's embedded OOXML timestamp is pinned to its source file's last
git commit time (`SOURCE_DATE_EPOCH`), so regenerating from an unchanged
source on the same `pandoc` version produces byte-identical output. A CI check
that flags a committed binary as drifted from its markdown source is a
tracked follow-up (it requires pinning the `pandoc` version in CI, since
output bytes differ across pandoc versions).
