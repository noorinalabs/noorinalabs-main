# Promotion Audit — p5-wave-4 (2026-06-16)

## Result

| Tier | Outcome |
|------|---------|
| memory → charter | **0 AUTO** · 0 DECIDE — no memory crossed the citation threshold with `promotion_target: charter` + active + not-already-promoted. Clean (matches the skill's expected ~0-AUTO steady state). |
| section → skill / skill → hook | **NOT EMITTED** — the manual driver produced an untrustworthy AUTO count (24) for these tiers (signal mis-derivation: `count_skill_invocations(section.promoted_to, …)` with empty slugs). Deferred pending a canonical driver. |
| memory tier counts | 149 memories scanned · 4 SUPERSEDED · 21 ALREADY-PROMOTED · remainder KEPT. |

## Finding (process gap → tech-debt)

`/promotion-audit` ships pure `helpers.py` functions but **no canonical CLI driver** — the orchestrator hand-rolls the helper-call sequence (thresholds, signal wiring) inline each retro. The memory tier (called carefully) returned the correct 0 AUTO; the section/skill tiers (different signal plumbing) mis-fired to 24 AUTO. A deterministic `run.py {wave}` entry point would eliminate the per-retro re-implementation risk — same determinism-over-hand-rolling principle as main#688 (`wave_status.py`). Filed as a follow-up.

## Disposition

- Memory→charter promotions: none due this wave (authoritative).
- Section/skill artifacts: none emitted (driver not trustworthy); re-run after the canonical driver lands.
