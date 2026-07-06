---
name: project_donor_readiness_wave
description: Deferred donor-demo wave — narrator-centric product-readiness walkthrough; runs after streaming (W24) + ML (W25); critical-path scope preserved.
metadata:
  type: project
---

Owner prioritized a **fundraising/donor demo** (2026-07-05) and picked **Theme A** ("make the live product good to use") with a **narrator-centric** storyline and **no hard date**. When asked how to reconcile with the approved phase-8 plan (W24=streaming, W25=ML), owner chose **"donor wave after the planned work"** — i.e. finish the committed analytical-depth waves first, then the donor wave.

**Sequencing:** streaming (W24, `main#667`) → ML nucleus (W25, `main#775`) → **donor-readiness wave**. Off-theme for P8 (Analytical Depth), so it seeds the **Phase 9 opener** (or a P8 tail wave) — settled at `/plan-phase 9` on P8 exit. Recorded in `.claude/team/phases/phase-8.md` § Deferred.

**Demo = the spec (narrator-centric walkthrough), critical-path ordered:**
1. **da#317** — kill the matn-sentence / Qur'anic-verse narrator tail (~26% of narrators, mc≤1 zero-degree). A narrator-centric demo lives on clean narrator search/lists. `noorinalabs-data-acquisition`.
2. **ig#1166** — Graph Explorer `?narrator=` deep-link (renders id-first, ignores param). "Click narrator → see their isnad network" is the core interaction. `noorinalabs-isnad-graph` frontend.
3. **deploy#523** — semantic-search embedder parity (prod/stg API on hashing vs corpus MiniLM → 200-with-garbage). Hardens phase-8 **criterion #2** (ig#1148 is technically closed = returns 200 not 503, but results are low-quality until this lands). The long pole: cross-repo (deploy embed-service + isnad-graph search API + data-acquisition re-embed), touches prod (stg-gate + MVP prod-autonomy discipline). See [[project_semantic_embedder_parity]].
4. **da#318** — hadith matn served with raw `<NAR>/<SANAD>/<MATN>` markup (parser leak); surfaces when drilling into a hadith from a narrator.
5. **Visual-credibility pass** — design-system / landing polish so the whole walkthrough looks donor-ready (owner chose the "full polish" timeline bucket).

All five are currently `wave-23`-labeled carry-forward (open). At that wave's `/wave-scope`, relabel to the donor wave + apply +20% TD intake. Related: [[project_p7_narrator_pollution_resolve_fixes]] (da#317 origin), [[feedback_honest_audit_over_conclusion_claim]] (the ~26% tail is the honest un-weighted remainder behind #723's weighted closure).
