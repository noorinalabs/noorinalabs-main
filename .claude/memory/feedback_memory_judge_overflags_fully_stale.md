---
name: feedback_memory_judge_overflags_fully_stale
description: The Haiku content-staleness judge's "fully-stale" list is a set of candidates to verify, never a delete list — it has produced 9/9 false positives twice running by misreading placeholders, examples, external/child-repo refs and env vars as dead claims.
type: feedback
last_verified: 2026-07-27
promotion_target: skill
promotion_threshold:
  retro_citations: 3
status: active
---
`/memory-judge` (`.claude/skills/memory-judge/`, `.claude/agents/memory-judge.md`) resolves a note's backtick-quoted citations by grepping **this repo only**. Anything it cannot resolve that way it reports as stale. Its **fully-stale** bucket is therefore a list of *candidates to verify*, and must never be executed as a delete list. **Few or zero deletions is a success outcome, not a shortfall** (owner, standing).

**Track record — 18 flags, 18 false positives:**

| Pass | Fully-stale flagged | Genuinely dead |
|---|---|---|
| W28 retro Step 7.9 (108 notes, 96 due) | 9 | **0** |
| main#1139 re-verification (the same 9) | 9 | **0** |

**The five false-positive classes** (all observed; check each before believing a verdict):

1. **Placeholders in examples** — `user_steven.md` was flagged for `path/to/file.py`, which appears *inside the rule* "never cite a bare basename". `section_ci_tooling.md` for `[[slug]]`/`[[slug.md]]`.
2. **Child-repo citations** — the judge greps the parent. `feedback_role_class_specific_boundaries` cites `docs/runbooks/user-service-alembic.md`, which is in **noorinalabs-deploy** and exists. `feedback_cross_repo_wave_ref_resolution` describes deploy's `integration-tests.yml`, which still implements the prescribed pattern verbatim.
3. **External references** — GitHub Action refs (`actions/checkout@v4`), upstream repos (`rhysd/actionlint`), API routes, npm specs, remote/`~` paths, B2 object keys. Nothing in-repo to resolve.
4. **Deliberately-absent files** — `project_bootstrap_repo` asserts a file *was removed*; the judge flagged it as stale **for being right**. Verify the assertion's direction before acting.
5. **Category errors** — `section_<slug>.md` files are **section index files, not notes**. They have no frontmatter, so a `last_verified` bump on one is structurally impossible. A staleness verdict on one is meaningless.

**Also true, and the reason to still do the pass:** the judge is bad at precision but the *re-verification* is high-yield. main#1139 kept all 9 and still found, in those same notes, (a) `reference_ssh_topology` teaching a manual SSH-key append step made obsolete by deploy ADR 0006 — an actively harmful instruction, (b) `feedback_no_head_in_surface_enumeration` prescribing bare `grep`, hard-blocked since main#1008, and (c) the owner's email misspelled in `user_steven`. **None of those were what the judge flagged.** Run the pass, ignore the verdicts, read the notes.

**How to apply:** treat a fully-stale verdict as "read this note carefully", not "delete this note". Resolve every citation against the parent repo, **every child repo**, and external reality before concluding anything is dead. Where a note is genuinely superseded, set `superseded_by` on the old note rather than deleting it. Related: [[feedback_silent_zero_is_not_a_measurement]] (an unresolved grep is not evidence of absence).
