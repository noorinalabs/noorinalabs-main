# Agents — Governed Headcount

> Part of the [agents charter index](../agents.md) — re-shelved from `charter/agents.md` for section-level loading (#963). Rules unchanged.

## Governed Headcount (Roster Budget) <!-- promoted-to: lib/headcount_budget.py -->

The persona roster is **budgeted and machine-enforced** (persona Option B, P6 criterion #3 — decision in
`phase-6.md` § Criterion #3; analysis in `.claude/team/spikes/p6w2-persona-model-evaluation.md`). The spike
found the roster had drifted to ~2.5× the headcount the owner believed, with no budget and no gate — exactly
the "prose rule that decays because nothing enforces it" failure the enforcement hierarchy
(`feedback_enforcement_hierarchy.md`) warns about.

**The caps (single source of truth: `.claude/lib/headcount_budget.py`):**

| Roster | Cap (persona cards in `.claude/team/roster/`) |
|--------|-----------------------------------------------|
| Parent (`noorinalabs-main`) | **≤ 9** |
| Each child repo | **≤ 6** |

> **Cap history.** P6W17 (#841) first set the parent cap at 8 and slimmed the roster to 7. An owner revision
> (2026-06-24) raised it to **9**: two personas slated for retirement on a "0 parent commits" premise had in
> fact authored merged parent PRs that wave (Bereket #832/#846, Nino #838/#851 + review of #835), so they were
> kept; only the genuine duplicate (Aisha → Lucas) stays retired, leaving the parent roster AT 9.

**Enforcement.** `headcount_budget.py` counts `*.md` cards in `.claude/team/roster/` and HARD-BLOCKS (exit 1)
when the count exceeds the cap. It is wired exactly like the memory-budget gate (criterion #1): a `pre-push`
hook + a `Headcount budget gate` CI job, with the `headcount-budget` kind classified in
`pre_commit_ci_sync.py` so the sync-drift gate demands the local⇄CI mirror (#684). The parent run uses the
default (parent) budget; a child repo vendoring the gate invokes with `--budget 6`.

**Staying under budget — retire / merge, don't pile up.** When a roster is at cap and a new persona is
genuinely needed:

1. **Retire personas with no commits in the last N waves.** Removal is *card removal*: `git rm` the
   `roster/*.md` card. **Preserve history** — keep the name in `.claude/team/roster.json` (the commit-identity
   union manifest, so authored commits still resolve and `roster_union_sync.py` stays green) and **archive,
   don't delete,** their trust-matrix entries (add an "Archived Personas" note; leave their change-log rows in
   place). A deploy-repo persona whose canonical card lives in `noorinalabs-deploy` is retired from the parent
   by removing only the duplicate parent copy.
2. **Merge near-duplicate roles** (e.g. two same-titled engineers) into one card, retiring the staler.
3. Only if the roster has genuinely outgrown the cap, **raise the number deliberately** in
   `headcount_budget.py` (one reviewed line) — that is the surfaced decision the gate exists to force, the
   same posture as the memory-budget cap.

This composes with the P6 thesis: bias toward enforced, mechanical budgets over unmanaged narrative growth.

