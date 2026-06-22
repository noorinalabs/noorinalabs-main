# Spike — Ontology-vs-graphify (P6 end-state #4)

> **Status:** SPIKE COMPLETE — awaiting owner decision (keep / replace / hybrid).
> **Issue:** noorinalabs-main#728 · **Wave:** P6W2 (Architectural revisits) · **Author:** Weronika Zielinska (Platform Architect)
> **Decision nature:** spike-and-decide, NOT pre-commit (owner 2026-06-20). No teardown this phase; teardown (if chosen) follows the recorded decision in a later phase.

## 1. The question

Phase 6 criterion #4 asks whether the current **three-role ontology stack** —
Change Tracker (PostToolUse hook → `ontology/checksums.json`), Resolver (`/ontology-rebuild`),
Librarian (`/ontology-librarian`), plus the **Hook 15** consult gate
(`enforce_librarian_consulted`) — should be replaced by a simpler
**Google LLM-doc-format (`llms.txt`) + graphify** approach: auto-derive an LLM-readable
index and a code graph from the source instead of hand-curating YAML kept in sync by a
dirty-tracking state machine.

Owner directive 2026-06-19: "explore Google LLM-doc format + graphify to potentially drop
the ontology stack."

## 2. What was actually spiked

Child product repos are gitignored out of this checkout, so the **representative slice is the
meta-repo's own `.claude/` Python machinery** (`.claude/hooks/` + `.claude/lib/`) — ~19k LOC,
the very subsystem the ontology + memory describe. A ~60-line generator
(`ast`-based, stdlib only) was run over the slice to produce both candidate artifacts:

- an **`llms.txt`-style index** (one curated line per module, from its docstring), and
- a **code graph** (modules as nodes, intra-slice imports as edges, symbols per node).

### Measured results (real run, not estimated)

| Metric | Value |
|--------|-------|
| Modules indexed (nodes) | **54** |
| Intra-slice import edges | **57** |
| Top-level def/class symbols extracted | **418** |
| Modules already carrying a 1-line docstring | **54 / 54 (100%)** |
| Generated graph artifact size | **24 KB** (whole slice) |
| Generator size | **~60 LOC, stdlib `ast` only** |
| Hand-authoring required to produce the index | **0 lines** |

The 100%-docstring result is the load-bearing finding: the index and graph are **fully
auto-derivable from code that already exists**, regenerable on demand, and therefore
**structurally always-fresh** — there is no "dirty" state to track and no human step to
remember.

## 3. Comparison on the four axes (issue #728 acceptance)

| Axis | Current 3-role stack | `llms.txt` + graphify (spiked) |
|------|----------------------|-------------------------------|
| **Maintenance cost** | **1,347 LOC** of machinery (tracker 232 + Hook-15 475 + enforce_ontology_context 151 + sentinel helper + 2 skills) **plus 1,760 lines** of hand-curated YAML/MD payload that the Resolver must keep aligned. `checksums.json` is **88 KB** tracking **248 files**; **49** `ontology: rebuild` commits in history. | **~60 LOC** generator, **0** hand-authored payload for the code-derived layer. No checksums file, no resolver runs. |
| **Freshness / staleness** | *Eventual consistency.* Files go "dirty" (`last_tracked != last_resolved`) and stay stale until a human runs `/ontology-rebuild`. The whole tracker exists to **measure** drift; drift still happens. | *Structural freshness.* Regenerate = current, by construction. No drift window, no staleness metric needed. |
| **Query usefulness** | **High for semantics it captures by hand**: domain entities (`narrator`, `id_prefix: "nar:"`), service topology + integration intent, conventions/ADRs ("why"). These are **not** derivable from code structure. | **High for structure**: "what calls this", "what's in this module", import blast-radius, symbol lookup — the questions a graph answers natively and the curated YAML answers poorly. **Weak on domain semantics and intent** — a graph cannot invent the *meaning* of `narrator` or *why* a convention exists. |
| **Hook-15 friction** | A hard PreToolUse gate on **every** Edit/Write org-wide, justified by "freshness depends on a human consulting first." Has needed repeated fixes (transcript-flush race #169, cwd-keyed sentinel fallback, worktree-cwd edge cases). It is a standing tax on every edit. | If freshness is structural, the **premise for a blocking consult gate largely disappears** — consultation becomes "read the generated index," needing no per-edit enforcement. Friction → ~0. |

### What graphify genuinely **cannot** replace

The code graph and `llms.txt` index reproduce the **structural / repos-`*.yaml`** layer for free,
but they do **not** reproduce:

- **Domain semantics** — `domain.yaml` entity meanings, `id_prefix` conventions, cross-repo
  relationships (the hadith/narrator model). Hand-authored knowledge, low churn.
- **Service topology & integration intent** — `services.yaml` (who calls whom and *why*),
  prod/stg asymmetries.
- **The "why" prose** — `conventions.md`, ADRs. Rationale is not in the code.

These three are real, valuable, and **not** the part that rots — they change rarely and are not
mechanically derivable. The part that rots (and drives the 1,347 LOC of upkeep machinery) is the
**code-structural layer**, which is exactly the part graphify auto-derives.

## 4. Options & migration cost

### Option A — Keep (status quo)
- **Cost:** none now; ongoing 1,347-LOC machinery upkeep + the per-edit Hook-15 tax + recurring
  Hook-15 plumbing bugs.
- **When right:** if the structural YAML layer is considered high-value enough to justify hand-curation,
  or if churn is too low to bother changing.

### Option B — Replace (rip out the stack, go pure `llms.txt` + graph)
- **Migration:** delete tracker/resolver/librarian/Hook-15 + `checksums.json`; ship the generator +
  a regenerate-on-demand entry point; teach skills to read the generated index.
- **Cost:** medium (mostly deletion + a small generator already prototyped).
- **Risk:** **loses the domain/semantic/intent layer** that the graph cannot derive. Net regression
  on the "why" questions. **Not recommended as-is.**

### Option C — Hybrid (RECOMMENDED) — auto-derive structure, hand-curate semantics, drop the gate
- **Keep, as plain low-churn markdown/YAML (no dirty-tracking machinery):**
  `domain.yaml` semantics, `services.yaml` topology+intent, `conventions.md`/ADRs.
- **Replace with generated artifacts:** the `repos/*.yaml` structural layer + `api_surface` → an
  `llms.txt` index + code graph, regenerated on demand. Retire `checksums.json` and `/ontology-rebuild`
  for that layer.
- **Soften Hook 15:** since freshness becomes structural, downgrade the **blocking** consult gate to
  an advisory pointer (or scope it to edits that touch the hand-curated semantic layer). Removes the
  org-wide per-edit tax and the recurring transcript/cwd plumbing bugs.
- **Migration cost:** **low–medium**, and **incrementally shippable** — generator first, retire the
  structural-layer tracking second, soften Hook 15 last, each independently revertible.

## 5. Recommendation (for OWNER decision)

**Adopt Option C (Hybrid).** The spike shows the expensive, drift-prone half of the stack — the
code-structural layer plus its 1,347-LOC freshness machinery and per-edit Hook-15 tax — is **100%
auto-derivable** from code that already self-documents (54/54 docstrings) in ~60 LOC. The genuinely
valuable half — domain semantics, service intent, the "why" prose — is **not** what rots and should
stay hand-curated, but it does **not** need the tracker/resolver/checksums/Hook-15 apparatus to stay
fresh, because it isn't code-derived in the first place. Hybrid keeps everything that earns its keep
and deletes the machinery whose entire job is to chase drift that the graph approach makes
structurally impossible.

Pure-Replace is rejected: it would discard the semantic/intent layer the graph cannot reconstruct.
Keep is the do-nothing baseline and continues paying the upkeep + friction tax.

> **Per owner 2026-06-20 this spike does NOT tear anything out.** Implementation of the chosen
> option is deferred to a later phase, contingent on the decision recorded below and in
> `phase-6.md` §criterion #4.

---

## OWNER DECISION — to be recorded here and in `phase-6.md`

- [ ] **A — Keep** the current 3-role stack as-is.
- [ ] **C — Hybrid** (recommended): generate the structural layer (`llms.txt` + graph), retain
      hand-curated semantics/intent as low-churn markdown, soften Hook 15 to advisory. Teardown
      scheduled to a follow-up phase.
- [ ] **B — Replace** entirely with `llms.txt` + graph (accepting loss of the semantic/intent layer).

**Owner:** _______________  **Date:** _______________  **Notes:** _______________

_Follow-up implementation issue (only if B or C chosen): file against a later phase; do not action in P6._
