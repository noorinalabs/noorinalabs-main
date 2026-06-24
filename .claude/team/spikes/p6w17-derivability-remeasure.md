# Spike — Per-language structural-derivability re-measure on the product repos

> **Status:** **MEASURED 2026-06-24.** Per-language go/no-go below is the input gate for the Task 2 bake-off.
> **Issue:** noorinalabs-main#843 (Task 1, BLOCKING) · child of #820 (ontology **C × T2** execution) · **Wave:** P6W17
> **Author:** Weronika Zielinska (Platform Architect) · **Reviewers:** Nurul Hakim (primary), Aino Virtanen (secondary)
> **Predecessor:** `p6w2-ontology-vs-graphify.md` (#728) — which measured **Python/`ast` on the parent `.claude/` only** (54/54 modules, 100% docstrings). This spike RE-MEASURES on the **actual product repos, per language**, because that headline was explicitly flagged "proven for the parent slice, **unproven for the product**" (§2a-i of the predecessor).

---

## 0. TL;DR — go/no-go per language

| Language | Repos measured | Inventory/skeleton extractable? | Auto descriptions (doc-comment %) | Tooling | **Verdict** |
|----------|----------------|---------------------------------|-----------------------------------|---------|-------------|
| **Python** | isnad-graph, user-service, data-acquisition, isnad-ingest-platform, deploy, (landing/ds tooling) | **100%** (0/621 parse failures) | **91% module / 85% public-symbol** | stdlib `ast`, zero-dep | **GO** |
| **TypeScript / React** | isnad-graph FE, design-system, landing-page | **~100%** (ts-morph, 0 load errors) | **LOW — 11–17% in the big repos**, 55% landing | `ts-morph`/`tsc` (npm dep) | **GO for skeleton** — descriptions will NOT auto-populate; accept sparse index or hand-annotate the curated overlay |
| **Terraform / HCL** | deploy (30 `.tf`) | **100%** (0 parse failures) | **100% variables / 97% outputs** carry `description` | `python-hcl2` / `terraform` (avail) | **STRONG GO** (best of the stack) |
| **SQL** | user-service (ORM), embedded strings | **100%** via the Python path (declarative ORM) | inherits Python docstrings | `ast` + `sqlglot` (avail) | **GO** — no standalone `.sql` DDL exists; schema is SQLAlchemy models = Python |
| **Astro** | landing-page (11 `.astro`) | **Partial** — `ts-morph` does NOT parse `.astro`; needs `@astrojs/compiler` | n/a | astro compiler (extra dep) | **CONDITIONAL GO** — add an `.astro` frontmatter extractor; tiny surface (11 files) |
| **Cypher / Neo4j** | isnad-graph (11), data-acquisition (3), isnad-ingest-platform (3) | **Heuristic only** — no AST CLI in env; regex floor recovers labels/rel-types; DDL lives in **Python string literals** | n/a (query files carry no doc convention) | regex only (no mature CLI) | **NO-GO for an AST-generated index → hand-curated stub** (surface is tiny: 6 labels / 5 rel-types) |

**Bottom line:** the structural **skeleton** (modules/files, symbols, signatures, import edges) is **~100% mechanically derivable for Python, TS, HCL and SQL** — the generator approach is viable for the bulk of the polyglot stack. The two material caveats are (1) **TS doc-comment coverage is far lower than Python's**, so a TS index is symbol-rich but description-poor, and (2) **Cypher has no derivable structural layer worth generating** and should keep a small hand-curated stub. Astro needs one extra extractor.

---

## 1. What "derivable" means here (definition, so the % is honest)

The "structural layer" we are trying to auto-produce is the per-child `ontology/repos/*.yaml` content + the `api_surface` slices: a **file/module inventory**, the **key symbols** (defs/classes/exports/resources/tables), **import/dependency edges**, and a **one-line description** per element. A generator (`llms.txt` + code-graph, SCIP, etc.) produces this from source. Derivability splits into two independently-measured sub-dimensions:

1. **Skeleton extractability** — can a tool produce the inventory + symbols + edges + signatures at all, cleanly, with no hand-authoring? Measured as parse/load success and symbol yield. This is the part SCIP/llms.txt/code-graph exist to do.
2. **Auto-description coverage** — what fraction of symbols already carry a doc-comment the generator can lift into the index *for free*? This is the **auto-vs-hand-authored** fraction: where it is low, the generated index has names but not meaning, and intent must come from the hand-curated overlay (which C × T2 keeps anyway).

The predecessor's "100% auto-derivable" was the **skeleton** number for Python. The new question is whether skeleton extractability transfers across languages (it largely does) and what the description coverage looks like per language (it varies a lot).

## 2. Method (reproducible)

- All 7 product repos **cloned fresh from `origin/main`** (not the possibly-stale local sibling checkouts — issue #832) into a scratch dir. SHAs at measurement time: isnad-graph `1b87305`, user-service `d1c2d86`, data-acquisition `ce7f98d`, isnad-ingest-platform `346a887`, deploy `f9e9654`, landing-page `99cc31f`, design-system `6b0b39d`.
- Excluded `node_modules`, `.git`, `dist`, `build`, `.venv`, `__pycache__`, `.next`, `coverage`, `*.d.ts`.
- **Python:** stdlib `ast` — modules, top-level def/class symbols (public = no leading `_`, tests excluded for symbol/doc%), `import`/`from` edges, module + symbol docstring presence.
- **TS/TSX:** `ts-morph` (the TS compiler API) — source files, `getExportedDeclarations()`, `getImportDeclarations()`, JSDoc/TSDoc presence on exports; test files (`*.test/*.spec`, `__tests__`, `tests/`) excluded from export/doc counts.
- **HCL:** `python-hcl2` — block census (resource/variable/output/module/data/provider/locals), `description` presence on variables/outputs.
- **Cypher:** regex floor (no AST CLI available) — distinct node labels `(:Label)`, relationship types `[:REL]`, `CREATE CONSTRAINT/INDEX`, parameterised files.
- **SQL:** located via search — no standalone `.sql`; schema is SQLAlchemy declarative models (Python) + a few embedded DDL strings; `sqlglot` available for the embedded strings.
- Tool availability in env: `python3` 3.14, `node` 24 + `npx`, `terraform` 1.14, and on-demand `npm i typescript ts-morph` / `pip install sqlglot python-hcl2` all succeeded. **Not** available without their own install: `tsc` global, `tree-sitter`, `ctags`, `ast-grep`, `scip`.

Measurement scripts are reproduced in Appendix A.

## 3. Results

### 3.1 Python — `ast`, stdlib, zero-dependency

| repo | modules | (test) | module-doc % | public symbols | symbol-doc % | imports | parse fail |
|------|--------:|-------:|-------------:|---------------:|-------------:|--------:|-----------:|
| isnad-graph | 129 | 65 | 93.8 | 250 | 91.2 | 626 | 0 |
| user-service | 91 | 29 | 72.5 | 236 | 65.3 | 597 | 0 |
| data-acquisition | 187 | 99 | 94.1 | 198 | 97.0 | 1130 | 0 |
| isnad-ingest-platform | 181 | 80 | 93.9 | 242 | 93.8 | 1050 | 0 |
| deploy | 29 | 21 | 96.6 | 53 | 54.7 | 140 | 0 |
| landing-page | 2 | 0 | 100.0 | 10 | 70.0 | 9 | 0 |
| design-system | 2 | 1 | 100.0 | 5 | 80.0 | 10 | 0 |
| **TOTAL** | **621** | **295** | **91.0** | **994** | **84.6** | **3562** | **0** |

**Read:** skeleton extractability is **100%** (0/621 parse failures) — the parent-slice result transfers cleanly to the product's Python. Auto-description coverage is **strong** (91% module / 85% public-symbol org-wide). The weak repos are `deploy` scripts (54.7% — operational glue) and `user-service` (65.3%); even these are usable. **Python is the proven, zero-dep case — GO.**

### 3.2 TypeScript / React — `ts-morph`

| repo | source files | (test) | exported decls (non-test) | export-doc % | imports |
|------|-------------:|-------:|--------------------------:|-------------:|--------:|
| isnad-graph (frontend) | 147 | 64 | 212 | **10.8** | 562 |
| design-system | 68 | 12 | 429 | **16.8** | 183 |
| landing-page | 21 | 14 | 20 | 55.0 | 36 |

**Read:** the **skeleton is fully extractable** — ts-morph loaded every file with no errors and yielded 661 exported declarations + 781 import edges. **But auto-description coverage collapses vs Python: 10.8% / 16.8%** in the two substantial repos (TSDoc/JSDoc is simply not the team's habit in product TS). Implication for the generator: a TS structural index will be **symbol- and edge-rich but description-sparse**. That is fine for "what exports X / what imports Y / blast-radius" questions (which need names+edges, not prose) but means the *meaning* of a TS symbol must come from the hand-curated semantic overlay, not from lifted doc-comments. **GO for the skeleton; do not expect free descriptions.** (Note design-system's 429 exports — a component library where the export surface *is* the product; a strong, high-value generation target even at low doc%.)

### 3.3 Terraform / HCL — `python-hcl2`

deploy (30 `.tf`, **0 parse failures**): 21 resources · 46 variables · 38 outputs · 2 modules · 2 data sources · 5 providers · 3 locals. **Variable `description` coverage: 46/46 = 100%. Output `description` coverage: 37/38 = 97.4%.**

**Read:** the **best-derivable language in the stack.** HCL is declarative, and Terraform convention (lint-enforced) means variables/outputs already carry descriptions. Both skeleton **and** descriptions are essentially 100% auto-derivable. **STRONG GO.**

### 3.4 SQL — no standalone DDL; schema = SQLAlchemy (Python)

There are **no `.sql` files** in any repo. The relational schema is **SQLAlchemy declarative models** in `user-service/src/app/models/` (7 classes with `__tablename__`, 61 `Mapped[...]`/`mapped_column`/`Column` field declarations) plus Alembic migrations (Python) and a handful of embedded `CREATE TABLE` strings in Python (isnad-graph, isnad-ingest-platform). Therefore the "SQL structural layer" is **derivable through the Python `ast` path** (the models are already counted in §3.1's user-service row), with `sqlglot` available to parse the embedded DDL strings if a column-level schema is wanted. **GO — there is no separate SQL toolchain to stand up.**

### 3.5 Astro — partial gap

landing-page has 11 `.astro` files (6 declare a `Props` interface / use `Astro.props`). **`ts-morph` does not parse `.astro`**, so these are invisible to the TS extractor — a real coverage hole for landing-page's component surface. Closing it needs `@astrojs/compiler` to split frontmatter (which is TS, then extractable) from template. Surface is small (11 files). **CONDITIONAL GO — add an `.astro` extractor in the bake-off, or stub these 11 components until then.**

### 3.6 Cypher / Neo4j — heuristic only; the real schema hides in Python

The `.cypher` files are **named analysis/validation queries** (e.g. `bottleneck_narrators.cypher`, `chain_integrity.cypher`, `political_correlation.cypher`) — 11 in isnad-graph, 3 each in data-acquisition and isnad-ingest-platform. Two problems for a generator:

1. **No AST tool.** There is no mature Cypher AST CLI in the environment (no tree-sitter/ctags/scip either). Extraction is a **regex floor**: it recovers 6 distinct node labels (`Narrator`, `Hadith`, `Collection`, `Location`, `HistoricalEvent`, `USER`) and 5 relationship types (`NARRATED`, `TRANSMITTED_TO`, `APPEARS_IN`, `ACTIVE_DURING`, `PARALLEL_OF`) from isnad-graph — useful, but brittle and not a real parse.
2. **The graph DDL is not in the `.cypher` files at all.** `CREATE CONSTRAINT` (×2) and `CREATE (FULLTEXT/RANGE) INDEX` (×7) live as **string literals inside Python** (`src/utils/neo4j_client.py`, `src/cli.py`, `src/api/security.py`, `src/enrich/embeddings.py`). So even the schema-defining statements are reachable only by string-grep, not by parsing the `.cypher` corpus.

**Read:** there is **no clean, tool-supported structural artifact to generate** for Cypher, and the thing of value (the graph schema: 6 labels + 5 rel-types) is **already captured, hand-curated and low-churn, in `ontology/domain.yaml`**. Generating it adds brittleness for ~11 small query files. **NO-GO for an AST-generated index. Keep a hand-curated stub** — which mostly already exists as the domain graph model — plus, optionally, a one-line-per-file catalog of the named `.cypher` queries (filename → purpose), which is cheap to hand-maintain.

## 4. Which repos need a hand-curated structural stub

| Repo | Generated structural index covers | Needs hand-curated stub for |
|------|-----------------------------------|-----------------------------|
| **user-service** | 100% (pure Python + ORM) | — |
| **data-acquisition** | Python 100%; its 3 `.cypher` are covered by the shared graph stub | (Cypher slice → shared stub) |
| **isnad-ingest-platform** | Python 100%; ditto its 3 `.cypher` | (Cypher slice → shared stub) |
| **deploy** | Python 100% + HCL 100% | — |
| **design-system** | TS skeleton 100% (descriptions sparse) | optional: curated descriptions for the 429 exports |
| **landing-page** | TS skeleton 100% | **11 `.astro` components** until an astro extractor lands |
| **isnad-graph** | Python 100% + TS skeleton 100% | **Cypher graph-schema + query catalog** (shared stub) |

Net: exactly **one new hand-curated artifact is required — the Cypher/Neo4j graph-schema stub** (shareable across isnad-graph, data-acquisition, isnad-ingest-platform; largely already present in `domain.yaml`). landing-page needs the small `.astro` extractor or an interim 11-component stub. Everything else is generator-covered.

## 5. Hand-off to Task 2 (tooling bake-off)

- **Start the bake-off on isnad-graph** — it is the only repo that exercises Python + TS + Cypher together and so stresses every derivability boundary found here in one place.
- **Per-language go/no-go to feed the matrix:** Python **GO** (ast / SCIP-python), TS **GO** (ts-morph / scip-typescript — note low doc% when scoring "answer quality"), HCL **GO** (hcl2 / `terraform show -json`), SQL **GO** (via Python), Astro **conditional GO** (needs `@astrojs/compiler`), Cypher **NO-GO → stub**.
- **Scoring caveat for the bake-off's "answer quality" lens:** Python indexes will look great because descriptions ride along; TS indexes will look thin on description even when the symbol graph is complete. Score the **skeleton** and the **description** dimensions separately so TS isn't unfairly penalised for a doc-culture gap that the hand-curated overlay covers anyway.
- **No teardown / no commit of generator output this wave** — per the owner spike-and-decide directive, Task 3 (implementation) follows the bake-off after an owner checkpoint. This report is measurement + analysis only.

---

## Appendix A — measurement scripts

The three scripts below were run against fresh `origin/main` clones; they are deterministic and re-runnable. (Kept in-report rather than committed as tooling, since Task 3 — not this spike — owns any generator that ships.)

### A.1 Python (`ast`, stdlib)

```python
import ast, os, sys
EXCLUDE = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist",
           "build", ".next", "coverage", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
def iter_py(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in EXCLUDE]
        for fn in fns:
            if fn.endswith(".py"):
                yield os.path.join(dp, fn)
def measure(root):
    mods = doc = pub = pubdoc = imp = 0
    for path in iter_py(root):
        is_test = "test" in os.path.relpath(path, root).lower()
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        mods += 1
        if ast.get_docstring(tree): doc += 1
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not n.name.startswith("_") and not is_test:
                    pub += 1
                    if ast.get_docstring(n): pubdoc += 1
            if isinstance(n, (ast.Import, ast.ImportFrom)): imp += 1
    return mods, doc, pub, pubdoc, imp
# run: measure(<repo>) per repo; doc/mods = module-doc%, pubdoc/pub = symbol-doc%
```

### A.2 TS/TSX (`ts-morph`)

```js
import { Project, Node } from "ts-morph";
import path from "node:path";
const root = process.argv[2];
const project = new Project({ compilerOptions: { allowJs: true, jsx: 4 },
                              skipAddingFilesFromTsConfig: true });
project.addSourceFilesAtPaths([
  path.join(root, "**/*.{ts,tsx}"),
  "!" + path.join(root, "**/node_modules/**"),
  "!" + path.join(root, "**/{dist,build,.next,coverage}/**"),
  "!" + path.join(root, "**/*.d.ts"),
]);
let files = 0, exp = 0, expDoc = 0, imp = 0;
for (const sf of project.getSourceFiles()) {
  const fp = sf.getFilePath();
  files++;
  imp += sf.getImportDeclarations().length;
  if (/\.(test|spec)\.|__tests__|\/tests?\//.test(fp)) continue;
  for (const [, decls] of sf.getExportedDeclarations())
    for (const d of decls) {
      exp++;
      if (Node.isJSDocable(d) && d.getJsDocs().length > 0) expDoc++;
    }
}
console.log({ files, exp, export_doc_pct: Math.round(1000*expDoc/exp)/10, imp });
```

### A.3 HCL (`python-hcl2`) + Cypher (regex floor)

```python
import hcl2, os, re
# HCL: per .tf -> hcl2.load(f); census d.keys() (resource/variable/output/...);
#      variable/output description coverage = share whose body dict has "description".
# Cypher: per .cypher ->
LABEL = re.compile(r"\(\s*\w*\s*:\s*([A-Z][A-Za-z0-9_]+)")   # (:Label)
REL   = re.compile(r"\[\s*\w*\s*:\s*([A-Z_][A-Z0-9_]+)")     # [:REL_TYPE]
#   distinct labels/rel-types via set union across files; CREATE CONSTRAINT/INDEX via grep.
#   NOTE: graph DDL actually lives in Python string literals, not the .cypher files.
```
