---
name: feedback_orchestration_vs_product_balance
description: Owner flagged that waves have drifted into self-referential orchestration work; product repos are starved. Keep new process-issue intake tight and re-balance at wave-31.
metadata:
  type: feedback
last_verified: 2026-08-10
---

At wave-30 kickoff (2026-08-10) the owner observed: *"I feel like we have spent a
lot of time on orchestration and not a ton of time on product development and bug
fixes."* Presented with the option to re-scope wave-30, they chose to **proceed as
scoped** — with the caveat *"hope there's not a lot of new process related issues
that come up."*

**Why:** the observation is backed by numbers, not vibes.

- Wave-30 is **19 issues, 100% in `noorinalabs-main`** — a repo containing no
  product, only team config, hooks, skills, and lint helpers. Zero product code.
- Phase 10's own written plan (`.claude/team/phases/phase-10.md`, wave table)
  assigned wave-30 to **Track D (isnad-graph) + Track E (user-service)**. That was
  traded away at `/wave-scope 10 30` for the gate-precision theme, making phase 10
  **main-only for a third consecutive wave**.
- `noorinalabs-main` open-issue composition: **183 tech-debt / 117 process / 23 bug
  / 6 enhancement**. The process backlog is self-generated — wave-29 ran 45 PRs and
  produced most of it.
- Repo scope has been **narrowing**: w25 da-only → w26/27 main+da → w28 five repos
  → w29 two → w30 one.
- Meanwhile **199 open issues sit unscheduled across the product repos**
  (deploy 59, data-acquisition 53, isnad-graph 36, ingest-platform 22,
  landing-page 11, user-service 10, design-system 8).

The counter-argument is genuine and is why the wave stands: several scoped gates
actively block the lifecycle (#1138 STOPs `/wave-scope` itself; #1243 is a BLOCKING
gate that fails *open*; #1351 blocked the creation of the issue describing it).
This is not busywork — but it is a third wave of it.

**How to apply:**

1. **During wave-30 — tight intake.** File a new process/tech-debt issue only when
   it actually blocks a scoped story. Everything else goes to the wave-31 pool; do
   NOT expand scope mid-wave. Self-referential findings (a gate about a gate about
   a gate) are the specific thing to resist filing.
2. **At wave-31 scoping — re-balance is the default, not an option to raise.** The
   wave-30 scope note already records the carry: *"Tracks D and E now compress into
   waves 31–32."* Lead wave-31 scoping with Track D/E product work and treat further
   parent-repo process items as the thing that must justify itself.
3. **Report the split when scoping.** State product-repo vs parent-repo issue counts
   in the scope proposal so the balance is visible before the owner commits, rather
   than discovered after. Cf. [[feedback_state_the_denominator_with_the_number]].

Related: [[feedback_td_intake_20pct_per_wave]] (the intake gate that reports
"healthy" at BASE=0 over a 174-item pool — main#1374, scoped into wave-30),
[[feedback_wave_planning_from_board]].
