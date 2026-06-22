# Spike: Persona-model evaluation (value vs overhead)

- **Issue:** [noorinalabs-main#727](https://github.com/noorinalabs/noorinalabs-main/issues/727) — P6 end-state criterion #3
- **Author:** Nadia Khoury (Program Director)
- **Phase / wave:** Phase 6 (Claude Efficiency) / Wave 2 (Architectural revisits)
- **Type:** Spike-and-decide — **no teardown this wave.** Output is an evaluation + an owner-decision stub.
- **Date:** 2026-06-21

> Owner directive (2026-06-19): "revisit the persona model." Constrained (2026-06-20, `/plan-phase 6`)
> to **spike-and-decide, not pre-commit** — produce an evaluation and record an owner decision; any
> teardown/replacement follows the recorded decision in a later phase.

---

## 1. What the persona machinery actually is

The "persona model" is the simulated multi-person team that all work is routed through. It is not one
artifact but a stack of coupled artifacts:

| Artifact | Location | Role in the model |
|----------|----------|-------------------|
| Persona cards | `.claude/team/roster/*.md` (parent) + each child repo's `<repo>/.claude/team/roster/` | Named identity, personality, domain ownership, reviewer pairing |
| Name→email map | `.claude/team/roster.json` | Commit-identity source of truth (per-commit `-c` flags) |
| Charter (agents/commits/communication) | `.claude/team/charter/` | Rules that *reference* personas (spawn discipline, single-leader, reviewer pairing) |
| Trust matrix | `.claude/team/trust_matrix.md` | Per-engineer reliability scoring accumulated across waves |
| Feedback log | `.claude/team/feedback_log.md` | Per-persona + process feedback history |

### Reconciled headcount — the roster is larger than the owner believes

The issue and `phase-6.md` both cite **"≈28 personas."** That is an **undercount**. Ground-truth inventory
(taken 2026-06-21):

| Measure | Count | Source |
|---------|-------|--------|
| Named identities (commit-identity map) | **78** | `grep -cE '": "param' roster.json` |
| Canonical role-card files | **70** | 10 parent + 60 across 6 child rosters (`find -path '*/team/roster/*.md'`, excl. worktrees/node_modules) |
| Per-repo roster sizes | parent 10 · isnad-graph 16 · ingest 11 · data-acquisition 10 · design-system 8 · deploy 6 · landing-page 5 · user-service 4 | per-dir `ls` |
| On-disk card copies (incl. worktree dupes) | **349** | of which **279 live under `.claude/worktrees/*`** |

**Finding A (drift):** the roster has roughly **2.5–2.8×** the headcount the owner remembers. Nobody
re-counted as repos were added. This is itself the strongest single argument that the model accreted
without governance.

**Finding B (duplication surface):** 80% of on-disk card copies (279/349) are worktree duplicates. Each
worktree carries a full copy of every roster, so any card edit must reconcile against transient copies.
Low-severity, but it is real maintenance surface and a source of stale-card confusion.

---

## 2. Per-spawn cost (quantified)

Every code-writing spawn pays a fixed persona tax before it touches a line of code. From
`charter/agents.md` § Orchestrator checklist and the observed spawn flow:

| Cost component | What it is | Roughly |
|----------------|-----------|---------|
| Persona-card read | Orchestrator selects the "right" member, the agent loads its card | 50–60 lines context |
| `/ontology-librarian` invoke | Hook-15-mandated, per agent, cannot be inherited from parent | 1 skill round-trip + sentinel write |
| Commit-identity plumbing | Per-commit `-c user.name/-c user.email` from roster.json (never global) | per-commit ceremony, easy to get wrong |
| Worktree + per-repo worktree | Parent worktree + explicit child-repo worktree setup | 2 setup steps, lock/unlock lifecycle |
| Reviewer pairing | 2 named reviewers selected from roster, spawn-brief Requestor/Requestee fields | 2 extra spawns per PR |
| Trust-matrix / feedback bookkeeping | Retro updates per persona, per wave | amortized into `/wave-retro` |

The persona-specific portion of that tax is the **card-read + identity plumbing + reviewer-naming**. The
worktree and librarian costs are **not** persona costs — they would survive any restructuring (they are
isolation + ontology costs). This distinction matters for the options below: **restructuring personas does
not recover the worktree/librarian cost**, only the naming/identity/drift cost.

---

## 3. What the personas buy us (value)

Honest accounting — some of this value is real and load-bearing:

1. **Commit attribution & auditability** — per-commit identity gives a readable `git log` of who-did-what
   and a non-repudiable trail. This is genuinely useful and is the hardest value to replace.
2. **Reviewer diversity / 2-reviewer rule** — naming distinct reviewers operationalizes "two independent
   sets of eyes." The *diversity* value comes from the rule, not from the names being human-like.
3. **Trust matrix** — per-engineer reliability scoring that drives spawn decisions and feedback routing.
   Its signal is real but it is **keyed on persona identity**; collapse the identities and the matrix must
   be re-keyed (onto role-classes) or retired.
4. **Domain ownership / reviewer pairing** — cards encode who owns what subsystem. Useful for routing, but
   most of this is also encoded in `CODEOWNERS`-style locality and the repo map.
5. **Narrative legibility** — the simulated team makes multi-agent orchestration legible to the owner
   ("Aino flagged X, Santiago sequenced Y"). Soft value, but non-zero for a solo-owner dogfooding project.

---

## 4. What they cost (overhead)

1. **Roster drift** (Finding A) — headcount grew unmanaged to ~2.5× the believed size; no budget, no gate.
2. **Selection overhead** — the orchestrator must pick "the right named person" before every spawn, plus
   reviewer pairs. This is cognitive load that a role-class model would flatten.
3. **Identity-plumbing fragility** — per-commit `-c` flags are a recurring failure surface (see memories:
   commit-author gate, heredoc-in-commit, GIT_DIR leak, cross-persona task-claim hazard). Most are
   *identity-mechanism* bugs, not isolation bugs.
4. **Duplication maintenance** (Finding B) — 279 worktree card copies to keep from going stale.
5. **Bookkeeping** — trust-matrix (1638 lines) + feedback-log (3247 lines) grow per persona per wave; the
   per-persona granularity multiplies the surface that retros must touch.
6. **Cross-persona hazards** — TaskUpdate has no ownership guard; a mistyped taskId completes another
   persona's work (`feedback_cross_persona_task_claim_hazard`). More distinct personas = more collision space.

**Net read:** the *rules* the personas operationalize (2-reviewer, commit attribution, trust/feedback
discipline, single-leader spawn) carry most of the value. The *named-individual granularity at
~70–78 identities* carries most of the overhead and almost none of the incremental value over a smaller
role-class set.

---

## 4a. Finding C — the personality attributes are non-load-bearing context bloat (owner question 1)

Owner question (2026-06-22): the cards carry a lot of descriptive personality / non-technical
likes-dislikes that "don't seem to affect anything and just add context bloat." Tested directly: does any
persona personality attribute ever influence an output? Searched **every team doc except the roster cards
themselves** (the 1,639-line `trust_matrix.md` + all retro/feedback docs) for 12 distinct personality
tokens lifted from the cards.

| Tokens searched (drawn from the cards) | References found outside the roster cards |
|----------------------------------------|-------------------------------------------|
| jiu-jitsu · Finnish · sauna · churrasco · Nightwish · Sibelius · Lutheran · Catholic · rye bread · Codeforces · lo-fi · skiing | **0 (zero) — all twelve** |

**Result: zero.** Not one assessment, review, or retro in the project's history references a persona's
national origin, religion, sex, gender, musical taste, hobbies, or likes/dislikes. **Every** trust/feedback
entry is grounded in *technical delivery* (PRs, review catches, CI state, rework). The personality block is
**read on every spawn and referenced by nothing** — the owner's read is correct, and it is now measured.

Composition of the bloat (10 parent cards; the 60 child cards mirror the shape):
- Each card is ~50–64 lines. The static **Personality Profile** block — Communication Style + Background
  (incl. `National/Cultural Origin`, `Religion`, `Gender`, `Sex at Birth`) + Personal
  (`Likes` / `Dislikes` / `Music`) — is **~16–18 lines, roughly one third of every card.**
- That third is duplicated across **70 canonical cards + 279 worktree copies** (Finding B) and re-read on
  every persona spawn.

**The self-improvement scaffold the owner wants already half-exists but is under-used.** Every card already
carries `Tech Preferences — *Evolves based on project experience*` and 3 carry a `Performance History` with
per-session entries and trust deltas. Personas that *self-improve on retro feedback* is therefore a
**promotion of fields already in the schema**, not a new invention.

**Recommendation C (folds into Option B execution):** in the slim, **drop the demographic / taste
attributes that 0 assessments reference** (`National/Cultural Origin`, `Religion`, `Gender`, `Sex at Birth`,
`Music`, `Likes`, `Dislikes`). Keep at most a single terse, behaviour-shaping line where it demonstrably
affects routing (e.g. "review focus: systemic patterns" for a reviewer-class) — and only where a metric
supports it. Replace the freed space with a structured, **retro-fed `Learned Adjustments`** section: the
*only* evolving prose on a card becomes evidence-based feedback the retro appends, turning each persona into
a self-improving artifact instead of static fiction. Net: ~⅓ smaller cards, every remaining line either
load-bearing or evidence-derived.

---

## 4b. Finding D — the trust/feedback scoring is inflationary, with no firing path (owner question 2)

Owner observation (2026-06-22): "feedback is overly positive… everyone gravitates to a perfect score… no
one ever gets fired and after a few waves everyone is perfect." **Confirmed quantitatively** from
`trust_matrix.md`:

| Signal | Count | Reading |
|--------|-------|---------|
| Score **increases** (↑) | 35 | — |
| Score **decreases** (↓) | 3 | **~12:1 upward bias** |
| "Already at max" (pinned at 5) | 33 | ceiling-and-stick: once 5, never re-examined |
| Raised to **5** | 25 | — |
| Lowered to **2** | 2 | — |
| Lowered to **1** | 0 | no one is ever rated untrustworthy |
| "None this wave" / "None this phase" in the *Needs-Improvement* column | **139** | the improvement column is a formality |

Mechanics driving the inflation:
1. **Narrative, self-graded rubric.** Scores move on prose praise ("clean delivery," "reliable") rather
   than a mechanical metric. Praise is cheap; the default sentiment is positive.
2. **Monotone ratchet to a ceiling.** Increases vastly outnumber decreases and there is no decay, so scores
   only climb, then pin at 5 ("Already at max, no change" ×33).
3. **No negative-signal default.** Needs-Improvement defaults to "None this wave" (139×) instead of forcing
   either a specific gap or an explicit, evidence-backed "no actionable gap."
4. **No exit path.** Archival exists (Tariq / Mei-Lin "archived after Phase 8 reorganization") but it is
   **org-restructure-driven, never performance-driven.** Nothing maps sustained low delivery to
   non-spawn / retirement — hence "no one ever gets fired."

**Recommendation D (folds into Option B execution) — make scoring mechanical and bidirectional:**
- **Evidence-anchored deltas.** A trust change must cite a *countable* wave metric, not a narrative. The
  wrapup already computes per-wave counters (`changes_requested_cycles`, CI-red merges,
  `top_concentration_pct`); extend to per-engineer signals derivable from the merged-PR set: PRs merged,
  must-fix items *received* as author, must-fix items *caught* as reviewer, CI-red merges, rework cycles,
  review false-positives.
- **Decay toward neutral.** Absent a trust-relevant signal for N waves, a score drifts back toward 3 —
  defeats the ratchet-and-stick at 5.
- **Distribution discipline.** Reserve 5 for genuinely exceptional *relative* performance in the wave; not
  everyone can be 5 simultaneously. Calibrate against the mechanical metrics, not vibes.
- **Forced negative-signal pass.** Each retro records, per active engineer, either a specific evidence-backed
  gap or an explicit "metrics clean: {the numbers}." Ban bare "None."
- **Performance-triggered exit.** Define the demotion / retirement trigger (e.g. sustained bottom-tier
  mechanical metrics across K waves, or repeated CI-red merges) → persona archived / not spawned. Gives
  "fired" a concrete meaning and closes the loop the owner flagged.

These compose with the P6 thesis (criterion #1): **bias toward enforced, mechanical budgets / metrics over
unmanaged narrative.** Just as the memory-budget hook replaced unbounded prose memory, mechanical trust
metrics replace unbounded narrative praise.

---

## 5. Options

### Option A — Keep as-is
- **What:** No change. Roster stays at ~70 cards / 78 identities.
- **Pros:** Zero migration cost; narrative continuity; trust matrix keeps its history intact.
- **Cons:** Drift unaddressed and unbounded; selection + identity overhead persists; the owner's own
  directive ("revisit") is answered with "no change," which only makes sense if value clearly dominates —
  the evidence says it does not.
- **Migration cost:** none.

### Option B — Slim the roster (governed headcount)
- **What:** Cap each repo's roster at a small budget (e.g. parent ≤8, child ≤6), retire personas with no
  commits in the last N waves, merge near-duplicate roles. Add a **headcount-budget hook** mirroring the
  P6W1 MEMORY.md-budget approach (criterion #1). Keep named individuals, just fewer of them.
- **Pros:** Directly fixes Finding A (drift) with an enforced budget; preserves attribution/trust history
  for survivors; low conceptual change — the model is the same, just bounded.
- **Cons:** Doesn't address the *named-individual* selection/identity overhead, only its magnitude; picking
  who to retire is a judgment call; trust-matrix entries for retired personas must be archived.
- **Migration cost:** **low–moderate.** One audit pass + a budget hook + archive retired entries. No
  charter-rule rewrites.

### Option C — Restructure to role-classes (no named individuals)
- **What:** Replace named personas with **role-classes** (e.g. `program-director`, `reviewer`,
  `implementer:isnad-graph`, `standards-lead`). Commit identity becomes role-based
  (`role+isnad-graph-implementer@…`); reviewer pairing becomes "two distinct reviewer-role instances";
  trust matrix re-keys onto role-classes (or is retired in favor of the feedback log).
- **Pros:** Collapses 78 identities to ~8–12 classes; eliminates selection-by-name overhead and most
  drift surface; the *rules* (2-reviewer, single-leader, attribution-by-role) survive intact; identity
  plumbing simplifies (fewer, stable email locals).
- **Cons:** Loses per-individual narrative legibility and the accumulated per-person trust history (must
  re-key or retire); larger charter surface to rewrite (`agents.md`, `commits.md`, `communication.md`, and
  every "Requestor/Requestee" convention); reviewer-pairing-by-class needs a "two *distinct instances*"
  guard to preserve diversity. Highest blast radius.
- **Migration cost:** **high.** Charter rewrite across ≥3 files, roster.json restructure, trust-matrix
  migration, hook updates (commit-identity gate, validate_pr_review, reviewer-brief parser). This is a
  multi-wave teardown — exactly the kind of work P6 explicitly **defers to a later phase**.

---

## 6. Recommendation (for owner decision)

> **Owner decision (2026-06-22): Option B — DECIDED.** The owner has chosen to do Option B, and has
> scoped **two mandatory components into its execution**: (C) strip the non-load-bearing personality
> attributes and make personas self-improve on retro feedback (Finding C / §4a); and (D) replace the
> inflationary, self-graded scoring with mechanical, bidirectional, evidence-anchored trust metrics plus a
> performance-triggered exit path (Finding D / §4b). Both are now proven-out by the measurements above, not
> hypotheses. Execution remains deferred to a follow-up wave/phase per the P6 spike-and-decide directive;
> this wave records the decision and the scope.

**Recommend Option B (slim, governed) now, with Option C scoped as a deferred follow-up — NOT executed this wave.**

Rationale:
- The evidence shows the problem is primarily **ungoverned drift** (Finding A), not the existence of named
  personas. Option B fixes the actual measured problem (headcount 2.5× the believed size, no budget) with
  **low–moderate, mostly-mechanical** cost, and it composes with the P6 thesis: it is the *same*
  "bias toward enforced budgets over unmanaged prose" pattern as the W1 memory-budget hook (criterion #1).
- Option C is the architecturally cleaner end-state and is where the value/overhead math points long-term,
  **but** its migration cost is high and cross-cutting (charter + hooks + trust-matrix re-key). That is a
  *teardown*, and P6's owner directive (2026-06-20) explicitly says architectural revisits are
  **spike-and-decide, not pre-commit** — teardown follows the recorded decision in a **later phase**.
- Option A is not recommended: it answers a "revisit" directive with "no change" while the data shows
  unbounded drift and a clear overhead-dominates picture at the margin.

**Concretely, if the owner accepts the recommendation:**
1. This wave records the decision only (this doc + the `phase-6.md` stub). No cards are deleted.
2. A follow-up issue (P6W3 framework-debt or a later phase) executes Option B: roster audit + per-repo
   headcount-budget hook + archive of retired trust-matrix entries.
3. Option C is captured as a **future-phase ADR candidate** ("role-classes over named personas"), to be
   taken up only if Option B's governed-slim state still shows the named-individual overhead dominating.

**Open question for the owner:** narrative legibility (§3.5) is a genuine value of named personas for a
solo-owner dogfooding project. If the owner weights that highly, B is clearly correct (keeps names, bounds
count). If the owner weights efficiency over narrative, C becomes the preferred *eventual* end-state and the
follow-up should be an Option-C ADR rather than an Option-B audit.

---

## 7. Owner decision

> Recorded in `phase-6.md` § Criterion #3 — Persona-model decision. Status: **DECIDED (owner, 2026-06-22).**

| Field | Value |
|-------|-------|
| Decision | ☐ A (keep) · ☑ **B (slim, governed)** · ☐ C (restructure to role-classes) |
| Execution scope (folded in by owner) | **B + C-finding** (slim out non-load-bearing personality attrs → self-improving, retro-fed cards, §4a) **+ D-finding** (mechanical, bidirectional, decaying trust metrics + performance-triggered exit path, §4b) |
| Teardown this phase? | **No** (P6 = spike-and-decide; execution deferred per owner 2026-06-20) |
| Option C (role-classes) | Captured as a **deferred future-phase ADR candidate**, taken up only if governed-slim B still shows named-individual overhead dominating |
| Follow-up tracker | [noorinalabs-main#819](https://github.com/noorinalabs/noorinalabs-main/issues/819) — execution (B + §4a self-improving cards + §4b mechanical scoring), deferred to a later wave/phase |
